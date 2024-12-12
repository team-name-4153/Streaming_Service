
import subprocess
import os
from dotenv import load_dotenv
import sys
import boto3
import time

# def convert_to_hls(input_path, output_path):
#     command = [
#         'ffmpeg', '-i', input_path, '-profile:v', 'baseline', '-level', '3.0',
#         '-s', '640x360', '-start_number', '0', '-hls_time', '10', '-hls_list_size', '0',
#         '-f', 'hls', output_path
#     ]
    
#     subprocess.run(command, check=True)

def log_ffmpeg_output(stderr):
    for line in iter(stderr.readline, b''):
        print(line.decode('utf-8'), end='', file=sys.stderr)
        

def monitor_and_upload(stream_dir, user_id, stream_id, s3_client, uploaded_files, bucket_name='team-name', polling_interval=10):
    
    folder_key = f"{user_id}/{stream_id}/"
    print(folder_key, file=sys.stderr)
    while True:
        try:
            # List all files in the stream directory
            for root, dirs, files in os.walk(stream_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, stream_dir)
                    s3_key = os.path.join(folder_key, relative_path).replace("\\", "/")  # Ensure S3 key uses forward slashes

                    if s3_key not in uploaded_files:
                        try:
                            s3_client.upload_file(file_path, bucket_name, s3_key)
                            print(f"Uploaded {file_path} to s3://{bucket_name}/{s3_key}", file=sys.stderr)
                            uploaded_files.add(s3_key)
                        except Exception as upload_error:
                            print(f"Failed to upload {file_path} to S3: {upload_error}", file=sys.stderr)
            time.sleep(polling_interval)
        except Exception as e:
            print(f"Error in monitor_and_upload: {e}", file=sys.stderr)
            time.sleep(polling_interval)

def convert_to_hls(output_path):
    

    ffmpeg_command = [
        'ffmpeg',
        '-y',
        '-i', 'pipe:0',  # Read from standard input
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-tune', 'zerolatency',
        '-c:a', 'aac',
        '-ar', '44100',
        '-ac', '2',
        '-f', 'hls',
        '-hls_time', '2',
        '-hls_list_size', '0',
        output_path
    ]
    
    ffmpeg_process = subprocess.Popen(
        ffmpeg_command,
        stdin=subprocess.PIPE,     # Provide stdin for FFmpeg
        stderr=subprocess.PIPE     # Capture stderr for logging
    )

    return ffmpeg_process




def serialize_data(data):
    """
    Serializes a list of dictionaries containing MongoDB ObjectId to a JSON serializable format.
    """
    results = []
    for entry in data:
        # Convert each entry to a serializable form
        if '_id' in entry:
            entry['_id'] = str(entry['_id'])  # Convert ObjectId to string
        results.append(entry)
    return results

def create_folder(path):
    try:
        os.mkdir(path)
        print("Directory created successfully")
    except FileExistsError:
        print("Directory already exists")
    except FileNotFoundError:
        print("Parent directory does not exist")