import requests

def send_video():
    url = 'http://localhost:5000/upload-video'
    files = {'video': open('C:\BowenYang_SWE\cloud_computing\\final_project\\team-name\Streaming_Service\\testing_scripts\\test.mp4', 'rb')}
    data = {'userId': '123', 'startTime': '2021-01-01T12:00:00'}
    response = requests.post(url, files=files, data=data)
    print(response.text)

if __name__ == '__main__':
    send_video()