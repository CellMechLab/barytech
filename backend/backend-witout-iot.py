import threading
import random
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json

app = FastAPI()

# Allow CORS for frontend (adjust if necessary)
origins = [
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connected_clients = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"Client connected: {websocket}")
    try:
        while True:
            data = await websocket.receive_text()
            # Assume data is JSON formatted
            params = json.loads(data)
            print(f"mqtt client: {params}")
            # Publish to PAR topic
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"Client disconnected: {websocket}")

def send_random_data_to_clients():
    """Send random data to all connected clients every second."""
    while True:
        if connected_clients:
            data = f"Random data: {random.randint(0, 1000)}"
            print(f"Broadcasting: {data}")
            
            # Use asyncio to send the data to all WebSocket clients
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(broadcast_message(data))
            loop.close()

        # Sleep for 1 millisecond (1000 times per second)
        threading.Event().wait(0.01)

async def broadcast_message(message):
    """Broadcast a message to all connected WebSocket clients."""
    for client in connected_clients:
        try:
            await client.send_text(message)  # Send the message to the client
        except Exception as e:
            print(f"Error sending message to client: {e}")

if __name__ == "__main__":
    # Start the thread to send random data to WebSocket clients
    data_thread = threading.Thread(target=send_random_data_to_clients)
    data_thread.start()

    # Start the FastAPI server
    uvicorn.run(app, host="127.0.0.1", port=8000)
