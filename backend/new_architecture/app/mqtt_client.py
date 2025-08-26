import paho.mqtt.client as mqtt
from app.message_processor import process_message_batches, process_message_batches
import asyncio
import app.shared_state
import time
import queue
import orjson

mqtt_client = None

# Global counter for total received messages
total_messages_received = 0
# Message rate monitoring
last_message_count = 0
last_rate_check = time.time()

# Thread-safe queue for messages from MQTT thread to async event loop
message_queue = queue.Queue(maxsize=100000)


def get_mqtt_client():
    global mqtt_client
    if mqtt_client is None:
        raise RuntimeError("MQTT client is not initialized!")
    return mqtt_client


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
        client.subscribe("MON", qos=1)
    else:
        print(f"Failed to connect, return code {rc}")


def on_message(client, userdata, msg):
    """Callback for processing received MQTT messages."""
    global total_messages_received, last_message_count, last_rate_check

    # Increment the received message counter
    total_messages_received += 1
    
    # Monitor message rate every 5 seconds
    current_time = time.time()
    if current_time - last_rate_check >= 5:
        rate = (total_messages_received - last_message_count) / 5
        print(f"MQTT received - Message rate: {rate:.1f} msgs/sec, Total: {total_messages_received}")
        last_message_count = total_messages_received
        last_rate_check = current_time

    # OPTIMAL APPROACH: Minimal processing in MQTT thread
    # Just store the raw message payload for later processing
    try:
        # Store raw message in a simple list (thread-safe for single writer)
        if not hasattr(on_message, 'raw_messages'):
            on_message.raw_messages = []
        
        # Store the raw payload - no JSON parsing here!
        on_message.raw_messages.append(msg.payload)
        
    except Exception as e:
        print(f"Error storing MQTT message: {e}")


def start_mqtt_client():
    """Initialize and start the MQTT client."""
    global mqtt_client
    mqtt_client = mqtt.Client(client_id="subscriber_device_id", clean_session=False)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # Optimize for high message rates
    mqtt_client.max_inflight_messages_set(10000)  # Allow more in-flight messages
    mqtt_client.max_queued_messages_set(100000)   # Increase queue size

    mqtt_client.connect("127.0.0.1", 1883, keepalive=60)
    mqtt_client.loop_start()

async def process_raw_messages():
    """Process raw messages from MQTT thread efficiently."""
    print("Raw message processor started")
    
    while True:
        try:
            # Get raw messages from MQTT thread
            raw_messages = getattr(on_message, 'raw_messages', [])
            
            if not raw_messages:
                await asyncio.sleep(0.001)
                continue
            
            # Clear the raw messages list (thread-safe for single reader)
            on_message.raw_messages = []
            
            # Process all raw messages in batch
            if raw_messages:
                print(f"Processing batch of {len(raw_messages)} raw messages")
                await process_raw_message_batch(raw_messages)
                    
            await asyncio.sleep(0.001)  # Very short sleep
                        
        except Exception as e:
            print(f"Error in raw message processor: {e}")
            await asyncio.sleep(0.01)
    
async def process_raw_message_batch(raw_messages: list):
    """Process a batch of raw messages efficiently."""
    try:
        # Import here to avoid circular imports
        from app.message_processor import device_queues, device_config, start_device_broadcaster
        
        # Group messages by device
        device_messages = {}
        
        for raw_payload in raw_messages:
            try:
                # Parse JSON using orjson for faster processing
                message_content = orjson.loads(raw_payload)
                device_id = message_content.get("device_id")
                
                if device_id:
                    if device_id not in device_messages:
                        device_messages[device_id] = []
                    device_messages[device_id].append(message_content)
                    
            except Exception as e:
                print(f"Error parsing message: {e}")
                continue
        
        # Process each device's messages
        for device_id, messages in device_messages.items():
            # Initialize device config if needed
            if device_id not in device_config:
                device_config[device_id] = {"save_flag": False}
            
            # Ensure broadcaster is started for this device
            await start_device_broadcaster(device_id)
            
            # Put messages in device queue for broadcasting
            if device_id not in device_queues:
                device_queues[device_id] = asyncio.Queue()
                
            for message in messages:
                try:
                    device_queues[device_id].put_nowait(message)
                except asyncio.QueueFull:
                    print(f"Warning: Device queue full for {device_id}")
                    break
            
            # Save messages if save flag is enabled
            import app.shared_state
            print(f"Save flag value: {app.shared_state.save_flag}")
            if app.shared_state.save_flag:
                from app.message_processor import device_save_queues, start_device_saver
                print(f"Save flag is TRUE - saving messages for device {device_id}")
                await start_device_saver(device_id)
                for message in messages:
                    try:
                        device_save_queues[device_id].put_nowait(message)
                    except asyncio.QueueFull:
                        print(f"Warning: Save queue full for {device_id}")
                        break
            else:
                print(f"Save flag is FALSE - not saving messages for device {device_id}")
        
        print(f"Processed {len(raw_messages)} raw messages for {len(device_messages)} devices")
        
    except Exception as e:
        print(f"Error processing raw message batch: {e}")

__all__ = ["get_mqtt_client"]
