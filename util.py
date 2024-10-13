
import subprocess
import os


# def convert_to_hls(input_path, output_path):
#     command = [
#         'ffmpeg', '-i', input_path, '-profile:v', 'baseline', '-level', '3.0',
#         '-s', '640x360', '-start_number', '0', '-hls_time', '10', '-hls_list_size', '0',
#         '-f', 'hls', output_path
#     ]
    
#     subprocess.run(command, check=True)

def log_ffmpeg_output(stderr):
    for line in iter(stderr.readline, b''):
        print(line.decode('utf-8'), end='')
        
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