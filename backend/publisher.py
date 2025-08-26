import time
import math
import paho.mqtt.client as mqtt
import orjson
from datetime import datetime
import sys
import random

# MQTT Broker settings
broker = "127.0.0.1"
port = 1883
topic = "MON"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)

# CLI argument validation
if len(sys.argv) != 3:
    print("Usage: python publisher.py <points_per_batch> <total_points>")
    sys.exit(1)

try:
    points_per_batch = int(sys.argv[1])
    total_points = int(sys.argv[2])
except ValueError:
    print("Error: arguments must be integers.")
    sys.exit(1)

if points_per_batch <= 0 or total_points <= 0:
    print("Error: arguments must be positive integers.")
    sys.exit(1)

# MQTT client
client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=False)
client.on_connect = on_connect
client.connect(broker, port, 60)
client.loop_start()

total_messages_sent = 0

def generate_displacement(index):
    min_val = -1.2168244889861554e-6
    max_val = -3.203646967473276e-8
    scale = (max_val - min_val) / 2
    offset = (max_val + min_val) / 2
    return offset + scale * math.sin(math.radians(index))

def generate_force(index):
    base = 5e-12 * math.sin(math.radians(index * 3))
    noise = random.uniform(-5e-13, 5e-13)
    return base + noise

try:
    # Loop only while we still have points to send
    while total_messages_sent < total_points:
        start_time = time.time()
        messages_sent = 0

        for _ in range(points_per_batch):
            if total_messages_sent >= total_points:
                break

            disp = generate_displacement(total_messages_sent)
            force = generate_force(total_messages_sent)
            timestamp = datetime.now().isoformat()

            payload = {
                "displacement": disp,
                "force": force,
                "timestamp": timestamp,
                "device_id": "o0AMV2w1IoGL",
                "device_token": "dm31cNM1DQMmklhY",
            }

            # Use retain=False for streaming telemetry
            info = client.publish(topic, orjson.dumps(payload), qos=1, retain=False)
            # Optional: wait for QoS1 ack for each message (can be skipped for speed)
            # info.wait_for_publish()

            messages_sent += 1
            total_messages_sent += 1

        elapsed = time.time() - start_time
        time.sleep(max(0, 1 - elapsed))
        print(f"Sent {messages_sent} msgs this round, Total: {total_messages_sent}")

    print("All messages sent. Flushing in-flight publishes...")

    # Give a moment for any in-flight QoS1 messages to complete
    time.sleep(0.5)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    client.loop_stop()
    client.disconnect()
    print("Program finished.")
    sys.exit(0)
