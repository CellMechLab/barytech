import time
import random
import paho.mqtt.client as mqtt

# MQTT Broker settings
broker = "test.mosquitto.org"
port = 1883
topic = "wokwi/MON"

# Callback function for when the client connects to the broker
def on_connect(client, userdata, flags, rc):
    print("Connected with result code: " + str(rc))

# Create an MQTT client instance with persistent storage
client = mqtt.Client(client_id="PersistentClient", clean_session=False)

# Set the callback function
client.on_connect = on_connect

# Connect to the broker
client.connect(broker, port, 60)

# Start the loop to process callbacks
client.loop_start()

messages_sent = 0  # Counter to track the number of messages sent

try:
    while True:
        start_time = time.time()
        messages_sent = 0  # Reset counter for each second
        
        # Send 10000 messages
        for i in range(10000):
            # Generate random data
            data = f"Random data: {random.randint(0, 1000)}"
            client.publish(topic, data, qos=1)  # Example with QoS 1
            messages_sent += 1  # Increment the counter
        
        # Sleep to maintain 1000 messages per second
        elapsed_time = time.time() - start_time
        time_to_sleep = max(0, (1 - elapsed_time))  # Ensure we don't sleep negative time
        time.sleep(time_to_sleep)
        
        # Print how many messages were sent in the last second
        print(f"Messages sent in the last second: {messages_sent}")

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    # Stop the loop and disconnect
    client.loop_stop()
    client.disconnect()
