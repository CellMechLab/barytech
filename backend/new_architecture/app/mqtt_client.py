import paho.mqtt.client as mqtt
from app.message_processor import process_message_batches, process_message_batches
import asyncio
import app.shared_state

mqtt_client = None

# Global counter for total received messages
total_messages_received = 0


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
    global total_messages_received

    # Increment the received message counter
    total_messages_received += 1
    # print(f"Total messages received: {total_messages_received}")

    # Use the shared main event loop to schedule the async coroutine
    if app.shared_state.main_event_loop:
        asyncio.run_coroutine_threadsafe(process_message_batches(msg), app.shared_state.main_event_loop)
    else:
        print("Main event loop is not set. Cannot process message.")


def start_mqtt_client():
    """Initialize and start the MQTT client."""
    global mqtt_client
    mqtt_client = mqtt.Client(client_id="subscriber_device_id", clean_session=False)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    mqtt_client.connect("localhost", 1883, keepalive=60)
    mqtt_client.loop_start()
    

__all__ = ["get_mqtt_client"]
