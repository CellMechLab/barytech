import time
import math
import paho.mqtt.client as mqtt
import json
from datetime import datetime
import sys  # Import sys to access command-line arguments

# MQTT Broker settings
broker = "localhost"
port = 1883
topic = "MON"

# Callback function for when the client connects to the broker
def on_connect(client, userdata, flags, rc):
    print("Connected with result code: " + str(rc))

# Check for command-line arguments
if len(sys.argv) != 3:
    print("Usage: python publisher.py <points_per_batch> <total_points>")
    sys.exit(1)

try:
    # Read the points per batch and total points from command-line arguments
    points_per_batch = int(sys.argv[1])
    total_points = int(sys.argv[2])
except ValueError:
    print("Error: <points_per_batch> and <total_points> must be integers.")
    sys.exit(1)

if points_per_batch <= 0 or total_points <= 0:
    print("Error: <points_per_batch> and <total_points> must be positive integers.")
    sys.exit(1)

# Create an MQTT client instance with persistent storage
client = mqtt.Client(client_id="publisher_device_id", protocol=mqtt.MQTTv311, clean_session=False)

# Set the callback function
client.on_connect = on_connect

# Connect to the broker
client.connect(broker, port, 60)

# Start the loop to process callbacks
client.loop_start()

# Initialize accumulators
total_messages_sent = 0

try:
    while True:
        # Break the loop if the total messages sent exceeds or equals the total_points
        if total_messages_sent >= total_points:
            print("Maximum total points reached. Entering infinite sleep mode.")
            while True:
                time.sleep(1)  # Infinite sleep

        start_time = time.time()
        messages_sent = 0

        # Send up to points_per_batch messages or stop if total_points reached
        for i in range(points_per_batch):
            if total_messages_sent >= total_points:
                break

            # Generate sinusoidal data
            data1 = int(500 + 500 * math.sin(math.radians(total_messages_sent)))  # Scale to 0-1000 range
            data2 = int(500 + 500 * math.cos(math.radians(total_messages_sent)))  # Complementary sinusoidal pattern

            timestamp = datetime.now().isoformat()

            # Format data as JSON
            message = json.dumps({
                "displacement": data1,
                "force": data2,
                "timestamp": timestamp,
                "device_id": "3gP1kyIy6mp3",
                "device_token": "RgOQLO7uKJs0csmP",
            })

            # Publish the message
            client.publish(topic, message, qos=1)

            messages_sent += 1
            total_messages_sent += 1

        # Sleep to maintain approximately one batch per second
        elapsed_time = time.time() - start_time
        time_to_sleep = max(0, 1 - elapsed_time)
        time.sleep(time_to_sleep)

        # Print the number of messages sent in the last second and total messages sent
        print(f"Messages sent in the last second: {messages_sent}, Total messages sent: {total_messages_sent}")

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    # Stop the loop and disconnect
    client.loop_stop()
    client.disconnect()
    print("Program finished. All messages sent.")

