
from flask import Flask, render_template, send_from_directory, request, abort
from database.rds_database import rds_database
from models import Streaming_Service_Model
from dataclasses import asdict
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
from restful import error_response
from werkzeug.utils import secure_filename
from util import convert_to_hls, serialize_data, create_folder, log_ffmpeg_output
from flask_socketio import SocketIO, emit, disconnect
import threading
from werkzeug.utils import secure_filename
import jwt
from jwt.exceptions import InvalidTokenError

load_dotenv()
DB_NAME = os.getenv("RDS_DB_NAME")

BASEDIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

cur_database = rds_database(db_name=DB_NAME)
# cur_database = None


app.config['UPLOAD_FOLDER'] = 'storage/uploads/'
app.config['VIDEO_FOLDER'] = 'storage/videos/'
create_folder("storage")
create_folder(app.config['UPLOAD_FOLDER'])
create_folder(app.config['VIDEO_FOLDER'])

ffmpeg_processes = {}

# users_in_room = {}
# rooms_sid = {}
# names_sid = {}

########### TEST #############
@app.route('/')
def viewer():
    return render_template('viewer.html')

@app.route('/streamer')
def streamer():
    return render_template('streamer.html')

########### END TEST #############

@socketio.on('start_stream')
def start_streaming(payload):
    user_id = payload['user_id']
    stream_id = payload['stream_id']
    if not user_id or not stream_id:
        emit('error', {'error': 'Invalid stream ID or user ID'})
        return
    stream_dir = os.path.join(app.config['VIDEO_FOLDER'], str(user_id), str(stream_id))
    os.makedirs(stream_dir, exist_ok=True)

    stream_meta = Streaming_Service_Model.Stream_Meta(
            user_id=user_id,
            stream_id=stream_id,
            start_time=datetime.now(timezone.utc),
            end_time=None,
            hls_folder=stream_dir
        )
    res = cur_database.bulk_insert_data("streaming_meta", [asdict(stream_meta)])
    


@socketio.on('stop_stream')
def handle_stop_stream(payload):
    user_id = payload['user_id']
    stream_id = payload['stream_id']
    if not user_id or not stream_id:
        emit('error', {'error': 'Invalid stream ID or user ID'})
        return
    
    stream_key = (user_id, stream_id)
    if stream_key in ffmpeg_processes:
        ffmpeg_process = ffmpeg_processes.pop(stream_key, None)
        if ffmpeg_process:
            ffmpeg_process.stdin.close()
            ffmpeg_process.terminate()
            ffmpeg_process.wait()
            cur_database.update_data("streaming_meta", {"end_time": datetime.now(timezone.utc)}, {"user_id": user_id, "stream_id": stream_id})
            emit('stream_stopped', {'message': 'Stream has been stopped'})
        else:
            emit('error', {'error': 'Stream process not found'})
    else:
        emit('error', {'error': 'No active stream found for the provided IDs'})



@socketio.on('video_data')
def handle_video_data(payload):
    user_id = payload.get('user_id')
    stream_id = payload.get('stream_id')
    data = payload.get('data')

    if not all([user_id, stream_id, data]):
        emit('error', {'message': 'Missing user_id, stream_id, or data'})
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
        if stream_key not in ffmpeg_processes:
            stream_dir = os.path.join(app.config['VIDEO_FOLDER'], str(user_id), str(stream_id))
            os.makedirs(stream_dir, exist_ok=True)
            output_path = os.path.join(stream_dir, 'stream.m3u8')
            ffmpeg_process = convert_to_hls(output_path)
            ffmpeg_processes[stream_key] = ffmpeg_process
            threading.Thread(target=log_ffmpeg_output, args=(ffmpeg_process.stderr,), daemon=True).start()

        ffmpeg_process = ffmpeg_processes[stream_key]
        ffmpeg_process.stdin.write(data)
        ffmpeg_process.stdin.flush()
    except Exception as e:
        print(f"Error processing video data for {stream_id}: {str(e)}", file=sys.stderr)
        cleanup_stream(stream_key)
        emit('stream_error', {'message': 'Error processing stream'})

def cleanup_stream(stream_key):
    if stream_key in ffmpeg_processes:
        process = ffmpeg_processes.pop(stream_key, None)
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


@app.route('/watch/<path:filename>')
def watch_stream(filename):
    base_dir = os.path.abspath(app.config['VIDEO_FOLDER'])
    safe_filename = secure_filename(filename)
    requested_path = os.path.abspath(os.path.join(base_dir, filename))

    if not requested_path.startswith(base_dir):
        return error_response("Access denied.", 403)

    stream_dir = os.path.dirname(requested_path)
    file = os.path.basename(requested_path)

    if not os.path.isdir(stream_dir):
        return error_response("Stream directory not found: " + stream_dir, 404)

    if not os.path.isfile(requested_path):
        return error_response("File not found: " + requested_path, 404)

    return send_from_directory(stream_dir, file)


@app.route('/streams')
def list_streams():
    streams = cur_database.custom_query_data("SELECT * FROM streaming_meta WHERE end_time is NULL")
    return {'streams': streams}

@app.route('/videos')
def list_videos():
    streams = cur_database.custom_query_data("SELECT * FROM streaming_meta WHERE end_time is not NULL")
    return {'streams': streams}


@socketio.on("connect")
def on_connect():
    sid = request.sid
    print("New socket connected ", sid)

@socketio.on('connect')
def handle_connect():
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

@socketio.on("disconnect")
def on_disconnect(payload):
    sid = request.sid
    user_id = payload['user_id']
    stream_id = payload['stream_id']
    if not user_id or not stream_id:
        emit('error', {'error': 'Invalid stream ID or user ID'})
        return
    
    stream_key = (user_id, stream_id)
    if stream_key in ffmpeg_processes:
        ffmpeg_process = ffmpeg_processes.pop(stream_key, None)
        if ffmpeg_process:
            ffmpeg_process.stdin.close()
            ffmpeg_process.terminate()
            ffmpeg_process.wait()
            cur_database.update_data("streaming_meta", {"end_time": datetime.now(timezone.utc)}, {"user_id": user_id, "stream_id": stream_id})
            emit('stream_stopped', {'message': 'Stream has been stopped'})
        else:
            emit('error', {'error': 'Stream process not found'})
    else:
        emit('error', {'error': 'No active stream found for the provided IDs'})

# @socketio.on("join-room")
# def on_join_room(data):
#     sid = request.sid
#     room_id = data["room_id"]
#     display_name = data["name"]

#     # register sid to the room
#     join_room(room_id)
#     rooms_sid[sid] = room_id
#     names_sid[sid] = display_name

#     # broadcast to others in the room
#     print("[{}] New member joined: {}<{}>".format(room_id, display_name, sid))
#     emit("user-connect", {"sid": sid, "name": display_name},
#          broadcast=True, include_self=False, room=room_id)

#     # add to user list maintained on server
#     if room_id not in users_in_room:
#         users_in_room[room_id] = [sid]
#         emit("user-list", {"my_id": sid})  # send own id only
#     else:
#         usrlist = {u_id: names_sid[u_id]
#                    for u_id in users_in_room[room_id]}
#         # send list of existing users to the new member
#         emit("user-list", {"list": usrlist, "my_id": sid})
#         # add new member to user list maintained on server
#         users_in_room[room_id].append(sid)

#     print("\nusers: ", users_in_room, "\n")





# @socketio.on("data")
# def on_data(data):
#     sender_sid = data['sender_id']
#     target_sid = data['target_id']
#     if sender_sid != request.sid:
#         print("[Not supposed to happen!] request.sid and sender_id don't match!!!")

#     if data["type"] != "new-ice-candidate":
#         print('{} message from {} to {}'.format(
#             data["type"], sender_sid, target_sid))
#     socketio.emit('data', data, room=target_sid)


# TODO: delete this when comment server is done
# @socketio.on("send_message")
# def on_send_message(data):
#     target_sid = data['target_id']
#     sender_id = data['sender_id']
#     message = data['message']
#     requests.post("http://18.189.43.101:5000/comments/upload", json={ "comment": message, "userId": sender_id })
#     socketio.emit('message', data, room=target_sid)

################## REST

# @app.route('/upload-video', methods=['POST'])
# def upload_video():
#     video = request.files['video']
#     user_id = request.form['user_id']
#     start_time = request.form['startTime']

#     if video:
#         filename = secure_filename(video.filename)
#         video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#         video.save(video_path)

#         # Process video to HLS
#         hls_folder = os.path.join(app.config['VIDEO_FOLDER'], filename.rsplit('.', 1)[0])
#         os.makedirs(hls_folder, exist_ok=True)
#         hls_path = os.path.join(hls_folder, 'index.m3u8')
#         convert_to_hls(video_path, hls_path)
        
#         # Store metadata in MySQL
#         result = cur_database.bulk_insert_data("streaming_meta",[asdict(Streaming_Service_Model.Stream_Meta(user_id=user_id, start_time=start_time, hls_folder=hls_folder))])
#         return jsonify({"message": "Video uploaded and processed", "HLS URL": hls_path}), 200
#     return jsonify({"error": "No video file provided"}), 400


# @app.route('/stream/<int:user_id>')
# def stream(user_id):
#     result = cur_database.query_data('streaming_meta', columns=['user_id','id','hls_folder', 'start_time'], conditions={'user_id': user_id})
#     if len(result) == 0:
#         return {"Message":"Data Not Found"}
#     return send_from_directory(result[-1]['hls_folder'], 'index.m3u8')


# @app.route("/meta/<int:user_id>")
# def request_comments(user_id):
#     result = cur_database.query_data('streaming_meta', columns=['user_id','id','hls_folder', 'start_time'], conditions={'user_id': user_id})
#     result = serialize_data(result)
#     return jsonify(result)

if __name__ == '__main__':
    # app.run(debug=True, port=5000, host='0.0.0.0')
    socketio.run(app, debug=True, port=5000, host='0.0.0.0')

    
