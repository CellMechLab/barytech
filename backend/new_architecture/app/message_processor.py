import asyncio
import queue
import time
import json
from app.db import save_device_data_batch, get_db, get_user_id_by_device_id
from app.websocket_manager import websocket_connections  # Import the WebSocket connections dictionary
import app.shared_state
from datetime import datetime

device_queues = {} 
device_broadcasters = {}
# Accumulator to track total messages sent to the frontend
total_messages_sent_to_frontend = 0
# Batch queue for message processing
device_save_queues = {}       # device_id -> asyncio.Queue for saving
device_savers = {}            # device_id -> Task (saving)
device_config = {}            # device_id -> {"save_flag": bool, ... other config ...}

# Batch size and interval settings
BATCH_SIZE = 100  # Number of messages per batch
BATCH_INTERVAL = 5.0  # Time interval in seconds for processing batches

async def process_message_batches(msg):
    """Handles incoming MQTT messages, queues them for processing asynchronously."""
    try:
        # Decode the MQTT message payload and parse it into a dictionary
        message_content = json.loads(msg.payload.decode())  # Parse directly
        device_id = message_content.get("device_id")
        
        if device_id not in device_config:
            device_config[device_id] = {"save_flag": True}  # or fetch from DB/config
        # Ensure broadcaster is started for this device
        await start_device_broadcaster(device_id)

        # Put the parsed message into the queue for batch processing
        # await asyncio.get_running_loop().run_in_executor(None, message_queue.put, message_content)
        await device_queues[device_id].put(message_content)
        # Save the message to the database if the save_flag is enabled
        if device_config[device_id].get("save_flag", False):
            # print("app.shared_state.save_flag", app.shared_state.save_flag)
            await start_device_saver(device_id)
            await device_save_queues[device_id].put(message_content) 

    except json.JSONDecodeError as e:
        print(f"Error decoding MQTT message: {e}")
    except Exception as e:
        print(f"Error processing MQTT message: {e}")

async def start_device_broadcaster(device_id: str):
    """Starts a broadcaster task for a specific device_id, if not already started."""
    if device_id not in device_queues:
        device_queues[device_id] = asyncio.Queue()

    if device_id not in device_broadcasters:
        # Create the broadcaster task
        device_broadcasters [device_id] = asyncio.create_task(broadcast_messages(device_id))

async def start_device_saver(device_id: str):
    """Start a saver task if not started."""
    if device_id not in device_save_queues:
        device_save_queues[device_id] = asyncio.Queue()
    if device_id not in device_savers:
        device_savers[device_id] = asyncio.create_task(batch_processor(device_id))

async def batch_processor(device_id: str, batch_size: int = 100, interval: float = 5.0):
    """
    Continuously consumes messages for a specific device from its dedicated queue,
    batches them, and processes the batches.
    
    :param device_id: ID of the device to process.
    :param batch_size: Maximum number of messages per batch.
    :param interval: Time interval in seconds to wait before processing whatever
                     messages have accumulated even if not at full batch_size.
    """
    queue = device_save_queues[device_id]
    pending_messages = []
    last_flush = asyncio.get_event_loop().time()

    while True:
        try:
            # Wait for a message, or a timeout
            # timeout ensures that we periodically flush even if we don't get a full batch
            message = await asyncio.wait_for(queue.get(), timeout=interval)
            pending_messages.append(message)

            # If we hit the batch size, process the batch
            if len(pending_messages) >= batch_size:
                await process_batch(device_id, pending_messages)
                pending_messages.clear()
                last_flush = asyncio.get_event_loop().time()

        except asyncio.TimeoutError:
            # Interval passed without enough messages to fill a batch
            # Process what we have if there's anything pending
            if pending_messages:
                await process_batch(device_id, pending_messages)
                pending_messages.clear()
                last_flush = asyncio.get_event_loop().time()


async def process_batch(device_id: str, batch: list):
    """
    Processes a batch of messages and saves them to the database.
    """
    device_token = batch[0]["device_token"]

    async with get_db() as db:
        # Validate device once per batch
        # await validate_device(db, device_id, device_token)

        # Convert messages to records for bulk insert
        records = []
        for msg in batch:
            ts_str = msg["timestamp"].replace("Z", "+00:00")
            timestamp = datetime.fromisoformat(ts_str)

            records.append({
                "device_id": msg["device_id"],
                "timestamp": timestamp,
                "displacement": msg["displacement"],
                "force": msg["force"]
            })

        # Bulk insert
        await save_device_data_batch(db, records)

    print(f"Batch of {len(batch)} messages for device {device_id} saved successfully.")

# async def broadcast_messages():
#     """Batch messages and broadcast them to WebSocket clients."""
#     global total_messages_sent_to_frontend
#     while True:
#         batch = []
#         start_time = time.time()

#         try:
#             while time.time() - start_time < 1:  # Collect for up to 1 second
#                 try:
#                     message = message_queue.get_nowait()
#                     batch.append(message)
#                 except queue.Empty:
#                     await asyncio.sleep(0.01)  # Sleep briefly to avoid busy-waiting

#         except Exception as e:
#             print(f"Error collecting batch: {e}")

#         if batch:
#             print("Sending batch with size:", len(batch))
#             total_messages_sent_to_frontend += len(batch)  # Update the accumulator
#             print(f"Total messages sent to frontend: {total_messages_sent_to_frontend}")
#             await send_to_connected_clients(batch)

async def broadcast_messages(device_id: str):
    """Batch messages and broadcast them to WebSocket clients."""
    global total_messages_sent_to_frontend
    BATCH_SIZE = 10000  # Target batch size
    BATCH_TIMEOUT = 1  # Maximum time to wait for a batch (in seconds)
    queue = device_queues[device_id]

    while True:
        batch = []
        start_time = time.time()  # Track the time when batch collection started
        # Collect messages for the batch
        while len(batch) < BATCH_SIZE and (time.time() - start_time) < BATCH_TIMEOUT:
            try:    
                message = await asyncio.wait_for(queue.get(), timeout=0.1)
                batch.append(message)
            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)  # Sleep briefly to avoid busy-waiting

        # Send the batch if it's non-empty
        if batch:
            print(f"Sending batch with size: {len(batch)}")
            total_messages_sent_to_frontend += len(batch)  # Update the accumulator
            print(f"Total messages sent to frontend: {total_messages_sent_to_frontend}")
            
            async with get_db() as db:
                user_id = await get_user_id_by_device_id(db, device_id)
                
            await send_to_connected_clients(user_id, batch)
        else:
            # No messages collected in this cycle, sleep briefly to reduce CPU usage
            await asyncio.sleep(0.1)


async def send_to_connected_clients(client_id: str, messages: list):
    """Send a batch of messages to all connected WebSocket clients."""
    websockets = websocket_connections.get(client_id, set())
    print(websockets)
    if websockets:
        try:
            message_data = json.dumps(messages)
            tasks = [ws.send_text(message_data) for ws in websockets]
            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error broadcasting messages to user {client_id}: {e}")
    else:
        print(f"No active websocket connections found for user {client_id}")


def monitor_message_rate():
    """Monitor messages received per second."""
    while True:
        time.sleep(1)
        # Add logic to track and print the message rate
