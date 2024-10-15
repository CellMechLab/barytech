import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
import asyncio
import json

app = FastAPI()

# Define allowed origins
origins = [
    "http://localhost",
    "http://localhost:8080",  # Adjust based on your frontend's address
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connected_clients = []
buffered_messages = []

async def broadcast_message(message):
    """Send a message to all connected WebSocket clients."""
    if connected_clients:
        for client in connected_clients:
            try:
                await client.send_text(message)  # Await the send_text method
            except Exception as e:
                print(f"Error sending message to client: {e}")
    else:
        # Buffer the message if no clients are connected
        print(f"Pushed message to buffer: {message}")
        buffered_messages.append(message)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"Connected client: {websocket}")

    # Send any buffered messages to the newly connected client
    for msg in buffered_messages:
        print(f"Sending buffered msg: {msg}")
        await websocket.send_text(msg)

    try:
        while True:
            data = await websocket.receive_text()
            # Assume data is JSON formatted
            params = json.loads(data)
            print(f"Received from WebSocket: {params}")
            
            # Publish to PAR topic
            mqtt_client.publish("wokwi/PAR", json.dumps(params))
            print(f"Published to wokwi/PAR: {params}")

    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"Disconnected client: {websocket}")

# MQTT Callback functions
def on_connect(client, userdata, flags, rc):
    """Callback when the client receives a CONNACK response from the server."""
    if rc == 0:
        print("Connected to MQTT Broker!")
        client.subscribe("wokwi/MON")  # Subscribe to the topic
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    """Callback when a message is received from the broker."""
    message = msg.payload.decode()
    print(f"Received message: {message} on topic {msg.topic}")

    # Create a new task to broadcast the message asynchronously
    asyncio.run(broadcast_message(message))  # Run the coroutine

def start_mqtt_client():
    """Start the MQTT client."""
    global mqtt_client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.connect("test.mosquitto.org", 1883, keepalive=60)
        mqtt_client.loop_start()  # Start the MQTT client loop
    except Exception as e:
        print(f"Could not connect to MQTT Broker: {e}")

if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=start_mqtt_client)
    mqtt_thread.start()  # Start the MQTT client in a separate thread
    uvicorn.run(app, host="127.0.0.1", port=8000)
