
import subprocess
from flask import Flask, render_template, send_from_directory, request, jsonify
from database.rds_database import rds_database
from dataclasses import asdict
import os
from dotenv import load_dotenv
from restful import error_response
from streaming_socket import StreamingSocket
from werkzeug.utils import secure_filename
from util import convert_to_hls, serialize_data, create_folder, log_ffmpeg_output
from flask_socketio import SocketIO
from flask_cors import CORS
import sys
from pathlib import Path

load_dotenv()
DB_NAME = os.getenv("RDS_DB_NAME")

BASEDIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(app, cors_allowed_origins="*")

cur_database = rds_database(db_name=DB_NAME)
# cur_database = None
JWT_SECRET = os.getenv('JWT_SECRET', 'your_jwt_secret_key')
JWT_ALGORITHM = 'HS256'

app.config['VIDEO_FOLDER'] = 'storage/videos/'
create_folder("storage")
create_folder(app.config['VIDEO_FOLDER'])

app.config['COVER_FOLDER'] = 'storage/covers/'
create_folder(app.config['COVER_FOLDER'])


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

@app.route('/cover/<path:filename>')
def cover_stream(filename):
    base_dir = os.path.abspath(app.config['VIDEO_FOLDER'])
    requested_path = os.path.abspath(os.path.join(base_dir, filename))
    if not requested_path.startswith(base_dir):
        return error_response("Access denied.", 403)
    stream_dir = os.path.dirname(requested_path)
    if not os.path.isdir(stream_dir):
        return error_response("Stream directory not found: " + stream_dir, 404)
    

    ts_path = Path(stream_dir)
    if not ts_path.exists():
        raise FileNotFoundError(f"Directory {stream_dir} does not exist.")
    ts_files = list(ts_path.glob("*.ts"))
    latest_ts_file = max(ts_files, key=lambda f: f.stat().st_mtime)
    ts_files.remove(latest_ts_file)  # Remove the latest file
    second_latest_ts_file = None
    if ts_files:
        second_latest_ts_file = max(ts_files, key=lambda f: f.stat().st_mtime)

    image_name = str(stream_dir).replace('/',  '_')
    image_name = os.path.basename(image_name)
    valid_extensions = ['.jpg', '.jpeg', '.png']
    _, ext = os.path.splitext(image_name)
    if ext.lower() not in valid_extensions:
        ext = '.jpg'  # Default extension
        image_name += ext

    cover_folder = os.path.abspath(app.config['COVER_FOLDER'])

    output_image_path = os.path.join(cover_folder, image_name)
    for ts in [latest_ts_file, second_latest_ts_file]:
        if not ts: continue

        command = [
            'ffmpeg',
            '-i', str(latest_ts_file),       # Input file
            '-ss', "00:00:01",               # Seek to the specified time
            '-frames:v', '1',                # Extract one frame
            '-q:v', '2',                     # Quality for JPEG (optional)
            '-y',                            # Overwrite output file without asking
            output_image_path                # Output image file with extension
        ]

        try:
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode()
            print("Error extracting frame:", error_msg, file=sys.stderr)
            return error_response(f"FFmpeg failed: {error_msg}", 500)
        
        if os.path.exists(output_image_path):
            break
        
    if not os.path.exists(output_image_path):
        
        print(latest_ts_file, file=sys.stderr)
        print(output_image_path, file=sys.stderr)
        return error_response("Image extraction failed.", 500)
    # Serve the image to the client
    return send_from_directory(cover_folder, image_name, mimetype='image/jpeg')


streaming_namespace = StreamingSocket(
    namespace='/stream',
    video_folder=app.config['VIDEO_FOLDER'],
    database=cur_database,
    jwt_secret=JWT_SECRET,
    jwt_algorithm=JWT_ALGORITHM
)
socketio.on_namespace(streaming_namespace)


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000, host='0.0.0.0')

    
