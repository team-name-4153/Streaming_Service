
from flask import Flask, render_template, Response, send_from_directory, request, jsonify
# from Comment_Service.database.mongodb_database import database
from database.rds_database import rds_database
from models import Streaming_Service_Model
from dataclasses import asdict
import os
import sys
import json
from dotenv import load_dotenv
import subprocess
from werkzeug.utils import secure_filename
from util import *
load_dotenv()
DB_NAME = os.getenv("RDS_DB_NAME")



BASEDIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
cur_database = rds_database(db_name=DB_NAME)



app = Flask(__name__)
# Currently uploaded video will have long term storage. Could change implementation 
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['VIDEO_FOLDER'] = 'videos/'


@app.route('/upload-video', methods=['POST'])
def upload_video():
    video = request.files['video']
    user_id = request.form['userId']
    start_time = request.form['startTime']

    if video:
        filename = secure_filename(video.filename)
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        video.save(video_path)

        # Process video to HLS
        hls_folder = os.path.join(app.config['VIDEO_FOLDER'], filename.rsplit('.', 1)[0])
        os.makedirs(hls_folder, exist_ok=True)
        hls_path = os.path.join(hls_folder, 'index.m3u8')
        convert_to_hls(video_path, hls_path)
        
        # Store metadata in MySQL
        result = cur_database.bulk_insert_data("streaming_meta",[asdict(Streaming_Service_Model.Stream_Meta(userId=user_id, start_time=start_time, hls_folder=hls_folder))])
        return jsonify({"message": "Video uploaded and processed", "HLS URL": hls_path}), 200
    return jsonify({"error": "No video file provided"}), 400


@app.route('/stream/<int:userId>')
def stream(userId):
    result = cur_database.query_data('comments', columns=['userId','id','hls_folder', 'start_time'], conditions={'userId': userId})
    return send_from_directory(result[-1]['hls_folder'], 'index.m3u8')


@app.route("/meta/<int:userId>")
def request_comments(userId):
    result = cur_database.query_data('comments', columns=['userId','id','hls_folder', 'start_time'], conditions={'userId': userId})
    result = serialize_data(result)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
    
