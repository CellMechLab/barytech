import threading
import uvicorn
from app.mqtt_client import start_mqtt_client

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Define allowed origins
origins = [
    "http://localhost",
    "http://localhost:8080",  # Adjust based on your frontend's address
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    # mqtt_thread = threading.Thread(target=start_mqtt_client)
    # mqtt_thread.start()

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
