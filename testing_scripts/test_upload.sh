#!/bin/bash

curl -X POST http://10.206.119.241:5000/upload-video \
    -F "video=@C:\BowenYang_SWE\cloud_computing\final_project\team-name\Streaming_Service\testing_scripts\test.mp4" \
    -F "userId=123" \
    -F "startTime=2021-01-01T12:00:00"
