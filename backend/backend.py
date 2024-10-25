import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
import asyncio
import json
import time
import queue

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

# Global variables
connected_clients = []
buffered_messages = []
message_queue = queue.Queue()  # Queue for incoming messages
lock = threading.Lock()

# Message rate variables
message_count = 0

async def broadcast_message(messages):
    """Send a batch of messages to all connected WebSocket clients."""
    if connected_clients:
        message_data = json.dumps(messages)  # Convert the list of messages to JSON
        for client in connected_clients:
            try:
                await client.send_text(message_data)  # Send the batch message
            except Exception as e:
                print(f"Error sending message to client: {e}")
    else:
        # Buffer the message if no clients are connected
        buffered_messages.extend(messages)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"Connected client: {websocket}")

    # Send any buffered messages to the newly connected client
    if buffered_messages:
        buffered_data = json.dumps(buffered_messages)  # Convert the buffered messages to JSON array
        await websocket.send_text(buffered_data)  # Send all buffered messages at once
        print(f"Sent buffered messages: {len(buffered_messages)}")

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
    global message_count
    message = msg.payload.decode()
    
    # Add message to the queue for batch processing
    message_queue.put(message)
    
    with lock:
        message_count += 1  # Increment message count

def process_message_batches():
    """Process messages from the queue and send them in batches."""
    while True:
        messages = []
        try:
            for _ in range(100):  # Collect up to 100 messages for batch processing
                messages.append(message_queue.get_nowait())
        except queue.Empty:
            pass

        if messages:
            asyncio.run(broadcast_message(messages))  # Send batch of messages

        time.sleep(0.1)  # Control the frequency of batch processing

def monitor_message_rate():
    """Monitor the number of messages received per second."""
    global message_count
    while True:
        time.sleep(1)  # Wait for 1 second
        with lock:
            print(f"Messages received in the last second: {message_count}")
            message_count = 0  # Reset the counter for the next second

def start_mqtt_client():
    """Start the MQTT client."""
    global mqtt_client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.connect("localhost", 1883, keepalive=60)
        mqtt_client.loop_start()  # Start the MQTT client loop
    except Exception as e:
        print(f"Could not connect to MQTT Broker: {e}")

if __name__ == "__main__":
    mqtt_thread = threading.Thread(target=start_mqtt_client)
    mqtt_thread.start()  # Start the MQTT client in a separate thread

    # Start the message processing and monitoring threads
    threading.Thread(target=process_message_batches, daemon=True).start()
    threading.Thread(target=monitor_message_rate, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=8000)
