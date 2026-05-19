from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import cv2

app = FastAPI()

def get_camera():
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        # fallback for Raspberry Pi camera module
        cam = cv2.VideoCapture(
            "libcamerasrc ! video/x-raw, width=640, height=480, framerate=30/1 ! "
            "videoconvert ! appsink",
            cv2.CAP_GSTREAMER
        )
    return cam

camera = get_camera()

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            continue
        
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.get("/video")
def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
