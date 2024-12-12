
from flask import request
from flask_socketio import Namespace, emit, disconnect
import os
import threading
from datetime import datetime, timezone
import jwt
from jwt import PyJWTError
from middleware import token_required_socket
from models import Streaming_Service_Model
from database.rds_database import rds_database
from util import convert_to_hls, log_ffmpeg_output, monitor_and_upload
from dataclasses import asdict
import sys
from dotenv import load_dotenv
import boto3

load_dotenv()
s3 = boto3.client('s3',
                  aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                  aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                  region_name='us-east-2')


# emit: all emit has a message
#     connected
#     error
#     stream_started
#     stream_stopped
#     stream_error: when the data passed to stream is invalid

class StreamingSocket(Namespace):
    def __init__(self, namespace, video_folder, database, jwt_secret, jwt_algorithm):
        super().__init__(namespace)
        self.video_folder = video_folder
        self.database = database
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.ffmpeg_processes = {}
        self.sid_to_info = {}
        self.uploaded_files = {}
        self.process_lock = threading.Lock()

    # @token_required_socket
    def on_connect(self):
        sid = request.sid
        token = request.args.get('token')

        emit('connected', {'message': 'Successfully connected'})
        # if not token:
        #     print("Connection rejected: No token provided")
        #     emit('error', {'message': 'Authentication token is missing'})
        #     disconnect()
        #     return

        # try:
        #     payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        #     print(f"User {payload['user_id']} connected with SID {request.sid}")
        #     emit('authenticated', {'message': 'Successfully authenticated'})
        # except InvalidTokenError:
        #     print("Connection rejected: Invalid token")
        #     emit('error', {'message': 'Invalid authentication token'})
        #     disconnect()

    def on_disconnect(self):
        sid = request.sid
        info = self.sid_to_info.pop(sid, None)
        if not info:
            emit('error', {'message': 'Invalid socket session.'})
            return
        
        user_id = str(info["user_id"])
        stream_id = info["stream_id"]

        if not user_id or not stream_id:
            emit('error', {'message': 'Invalid stream ID or user ID'})
            return
        
        stream_key = (user_id, stream_id)
        if stream_key in self.ffmpeg_processes:
            ffmpeg_process = self.ffmpeg_processes.pop(stream_key, None)
            if ffmpeg_process:
                ffmpeg_process.stdin.close()
                ffmpeg_process.terminate()
                ffmpeg_process.wait()
                # self.database.update_data("streaming_meta", {"end_time": datetime.now(timezone.utc)}, {"user_id": user_id, "stream_id": stream_id})
                emit('stream_stopped', {'message': 'Stream has been stopped'})
            else:
                emit('error', {'message': 'Stream process not found'})
        else:
            emit('error', {'message': 'No active stream found for the provided IDs'})

    def on_start_stream(self, payload):
        sid = request.sid
        user_id = str(payload['user_id'])
        stream_id = payload['stream_id']
        if not user_id or not stream_id:
            emit('error', {'message': 'Invalid stream ID or user ID'})
            return
        self.sid_to_info[sid] = {"user_id": user_id, "stream_id": stream_id}
        stream_dir = os.path.join(self.video_folder, str(user_id), str(stream_id))
        os.makedirs(stream_dir, exist_ok=True)

        # stream_meta = Streaming_Service_Model.Stream_Meta(
        #         user_id=user_id,
        #         stream_id=stream_id,
        #         start_time=datetime.now(timezone.utc),
        #         end_time=None,
        #         hls_folder=stream_dir
        #     )
        # res = self.database.bulk_insert_data("streaming_meta", [asdict(stream_meta)])
        emit('stream_started', {'message': 'Stream has started'})

    def on_stop_stream(self):
        sid = request.sid
        info = self.sid_to_info.pop(sid, None)
        if not info:
            emit('error', {'message': 'Invalid socket session.'})
            return
        
        user_id = str(info["user_id"])
        stream_id = info["stream_id"]
        
        stream_key = (user_id, stream_id)
        if stream_key in self.ffmpeg_processes:
            ffmpeg_process = self.ffmpeg_processes.pop(stream_key, None)
            if ffmpeg_process:
                ffmpeg_process.stdin.close()
                ffmpeg_process.terminate()
                ffmpeg_process.wait()
                # self.database.update_data("streaming_meta", {"end_time": datetime.now(timezone.utc)}, {"user_id": user_id, "stream_id": stream_id})
                emit('stream_stopped', {'message': 'Stream has been stopped'})
            else:
                emit('error', {'message': 'Stream process not found'})
        else:
            emit('error', {'message': 'No active stream found for the provided IDs'})

    def on_video_data(self, payload):
        sid = request.sid
        info = self.sid_to_info.get(sid, None)
        if not info:
            emit('error', {'message': 'Invalid socket session.'})
            return
        
        user_id = self.sid_to_info[sid].get("user_id", None)
        stream_id = self.sid_to_info[sid].get("stream_id", None)
        data = payload.get('data')
        if not data:
            emit('error', {'message': 'Missing data'})
            return
        try:
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

                # bucket = "team-name"
                # folder_key = f"{user_id}/{stream_id}/"
                # s3.put_object(Bucket=bucket, Key=folder_key)

                # uploaded_files = set()
                # self.uploaded_files[stream_key] = uploaded_files

                # threading.Thread(
                #     target=monitor_and_upload,
                #     args=(stream_dir, user_id, stream_id, s3, uploaded_files),
                #     daemon=True
                # ).start()
            

            ffmpeg_process = self.ffmpeg_processes[stream_key]
            stderr_output = ffmpeg_process.stderr.read().decode()  # Read and decode stderr
            if stderr_output:
                print(f"FFmpeg error: {stderr_output}")
            ffmpeg_process.stdin.write(data)
            ffmpeg_process.stdin.flush()
        except Exception as e:
            # self.cleanup_stream(stream_key)
            print("error: " + str(e), file=sys.stderr)
            emit('stream_error', {'message': 'Error processing stream'})

    def cleanup_stream(self, stream_key):
        if stream_key in self.ffmpeg_processes:
            process = self.ffmpeg_processes.pop(stream_key, None)
            if process:
                try:
                    process.stdin.close()
                except Exception as e:
                    emit('error', {'message': 'Clean up stream error: ' + str(e)})
                    pass
                try:
                    process.terminate()
                    process.wait()
                except Exception as e:
                    emit('error', {'message': 'Clean up stream error: ' + str(e)})