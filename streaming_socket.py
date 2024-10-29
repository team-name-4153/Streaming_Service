
from flask import request
from flask_socketio import Namespace, emit, disconnect
import os
import threading
from datetime import datetime, timezone
import jwt
from jwt import PyJWTError
from models import Streaming_Service_Model
from database.rds_database import rds_database
from util import convert_to_hls, log_ffmpeg_output
from dataclasses import asdict
import sys



class StreamingSocket(Namespace):
    def __init__(self, namespace, video_folder, database, jwt_secret, jwt_algorithm):
        super().__init__(namespace)
        self.video_folder = video_folder
        self.database = database
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.ffmpeg_processes = {}
        self.sid_to_info = {}
        self.process_lock = threading.Lock()


    def on_connect(self):
        sid = request.sid
        token = request.args.get('token')
        # if not token:
        #     print("Connection rejected: No token provided")
        #     emit('error', {'error': 'Authentication token is missing'})
        #     disconnect()
        #     return

        # try:
        #     payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        #     print(f"User {payload['user_id']} connected with SID {request.sid}")
        #     emit('authenticated', {'message': 'Successfully authenticated'})
        # except InvalidTokenError:
        #     print("Connection rejected: Invalid token")
        #     emit('error', {'error': 'Invalid authentication token'})
        #     disconnect()
    def on_disconnect(self):
        sid = request.sid
        info = self.sid_to_info.pop(sid, None)
        if not info:
            emit('error', {'error': 'Invalid socket session.'})
            return
        
        user_id = self.sid_to_info[sid]["user_id"]
        stream_id = self.sid_to_info[sid]["stream_id"]

        if not user_id or not stream_id:
            emit('error', {'error': 'Invalid stream ID or user ID'})
            return
        
        stream_key = (user_id, stream_id)
        if stream_key in self.ffmpeg_processes:
            ffmpeg_process = self.ffmpeg_processes.pop(stream_key, None)
            if ffmpeg_process:
                ffmpeg_process.stdin.close()
                ffmpeg_process.terminate()
                ffmpeg_process.wait()
                self.database.update_data("streaming_meta", {"end_time": datetime.now(timezone.utc)}, {"user_id": user_id, "stream_id": stream_id})
                emit('stream_stopped', {'message': 'Stream has been stopped'})
            else:
                emit('error', {'error': 'Stream process not found'})
        else:
            emit('error', {'error': 'No active stream found for the provided IDs'})

    def on_start_stream(self, payload):
        sid = request.sid
        user_id = payload['user_id']
        stream_id = payload['stream_id']
        if not user_id or not stream_id:
            emit('error', {'error': 'Invalid stream ID or user ID'})
            return
        self.sid_to_info[sid] = {"user_id": user_id, "stream_id": stream_id}
        stream_dir = os.path.join(self.video_folder, str(user_id), str(stream_id))
        os.makedirs(stream_dir, exist_ok=True)

        stream_meta = Streaming_Service_Model.Stream_Meta(
                user_id=user_id,
                stream_id=stream_id,
                start_time=datetime.now(timezone.utc),
                end_time=None,
                hls_folder=stream_dir
            )
        res = self.database.bulk_insert_data("streaming_meta", [asdict(stream_meta)])

    def on_stop_stream(self):
        sid = request.sid
        info = self.sid_to_info.pop(sid, None)
        if not info:
            emit('error', {'error': 'Invalid socket session.'})
            return
        
        user_id = self.sid_to_info[sid]["user_id"]
        stream_id = self.sid_to_info[sid]["stream_id"]
        
        stream_key = (user_id, stream_id)
        if stream_key in self.ffmpeg_processes:
            ffmpeg_process = self.ffmpeg_processes.pop(stream_key, None)
            if ffmpeg_process:
                ffmpeg_process.stdin.close()
                ffmpeg_process.terminate()
                ffmpeg_process.wait()
                self.database.update_data("streaming_meta", {"end_time": datetime.now(timezone.utc)}, {"user_id": user_id, "stream_id": stream_id})
                emit('stream_stopped', {'message': 'Stream has been stopped'})
            else:
                emit('error', {'error': 'Stream process not found'})
        else:
            emit('error', {'error': 'No active stream found for the provided IDs'})

    def on_video_data(self, payload):
        sid = request.sid
        info = self.sid_to_info.get(sid, None)
        if not info:
            emit('error', {'error': 'Invalid socket session.'})
            return
        
        user_id = self.sid_to_info[sid].get("user_id", None)
        stream_id = self.sid_to_info[sid].get("stream_id", None)
        data = payload.get('data')
        if not data:
            emit('error', {'message': 'Missing data'})
            return

        try:
            # Ensure data is in bytes
            if isinstance(data, list):
                data = bytes(data)
            elif isinstance(data, str):
                data = data.encode('utf-8')
            elif isinstance(data, bytes):
                pass
            else:
                data = bytes(data)

            stream_key = (user_id, stream_id)
            if stream_key not in self.ffmpeg_processes:
                stream_dir = os.path.join(self.video_folder, str(user_id), str(stream_id))
                os.makedirs(stream_dir, exist_ok=True)
                output_path = os.path.join(stream_dir, 'stream.m3u8')
                ffmpeg_process = convert_to_hls(output_path)
                self.ffmpeg_processes[stream_key] = ffmpeg_process
                threading.Thread(target=log_ffmpeg_output, args=(ffmpeg_process.stderr,), daemon=True).start()

            ffmpeg_process = self.ffmpeg_processes[stream_key]
            ffmpeg_process.stdin.write(data)
            ffmpeg_process.stdin.flush()
        except Exception as e:
            print(f"Error processing video data for {stream_id}: {str(e)}", file=sys.stderr)
            self.cleanup_stream(stream_key)
            emit('stream_error', {'message': 'Error processing stream'})

    def cleanup_stream(self, stream_key):
        if stream_key in self.ffmpeg_processes:
            process = self.ffmpeg_processes.pop(stream_key, None)
            if process:
                try:
                    process.stdin.close()
                except Exception as e:
                    print(f"Error closing stdin for stream {stream_key}: {str(e)}", file=sys.stderr)
                try:
                    process.terminate()
                    process.wait()
                except Exception as e:
                    print(f"Error terminating FFmpeg process for stream {stream_key}: {str(e)}", file=sys.stderr)