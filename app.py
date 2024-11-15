
from flask import Flask, render_template, send_from_directory
from database.rds_database import rds_database
from dataclasses import asdict
import os
from dotenv import load_dotenv
from restful import error_response
from streaming_socket import StreamingSocket
from werkzeug.utils import secure_filename
from util import convert_to_hls, serialize_data, create_folder, log_ffmpeg_output
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename

load_dotenv()
DB_NAME = os.getenv("RDS_DB_NAME")

BASEDIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

cur_database = rds_database(db_name=DB_NAME)
# cur_database = None
JWT_SECRET = os.getenv('JWT_SECRET', 'your_jwt_secret_key')
JWT_ALGORITHM = 'HS256'

app.config['UPLOAD_FOLDER'] = 'storage/uploads/'
app.config['VIDEO_FOLDER'] = 'storage/videos/'
create_folder("storage")
create_folder(app.config['UPLOAD_FOLDER'])
create_folder(app.config['VIDEO_FOLDER'])



########### TEST #############
@app.route('/')
def viewer():
    return render_template('viewer.html')

@app.route('/streamer')
def streamer():
    return render_template('streamer.html')

########### END TEST #############

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


streaming_namespace = StreamingSocket(
    namespace='/stream',
    video_folder=app.config['VIDEO_FOLDER'],
    database=cur_database,
    jwt_secret=JWT_SECRET,
    jwt_algorithm=JWT_ALGORITHM
)
socketio.on_namespace(streaming_namespace)


if __name__ == '__main__':
    # app.run(debug=True, port=5000, host='0.0.0.0')
    socketio.run(app, debug=True, port=5000, host='0.0.0.0')

    
