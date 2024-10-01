
import subprocess
import os 
import ffmpeg
# def convert_to_hls(input_path, output_path):
#     command = [
#         'ffmpeg', '-i', input_path, '-profile:v', 'baseline', '-level', '3.0',
#         '-s', '640x360', '-start_number', '0', '-hls_time', '10', '-hls_list_size', '0',
#         '-f', 'hls', output_path
#     ]
#     subprocess.run(command, check=True)


def convert_to_hls(input_path, output_path):
    (
        ffmpeg
        .input(input_path)
        .output(output_path, format='hls', start_number=0, hls_time=10, hls_list_size=0,
                video_bitrate='baseline', level='3.0', s='640x360')
        .run(overwrite_output=True)
    )

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