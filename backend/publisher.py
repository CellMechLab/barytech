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

try:
    while True:
        # Generate random data
        # data = f"Random data: {random.randint(0, 1000)}"
        # print(f"Broadcasting: {data}")
        
        # # Publish the data to the topic
        # client.publish(topic, data)

        # # Sleep for 1 second before sending the next message
        # time.sleep(1)
        start_time = time.time()
        for i in range(1000):
            # Generate random data
            data = f"Random data: {random.randint(0, 1000)}"
            print(f"Broadcasting: {data}")
            client.publish(topic, data, qos=1)  # Example with QoS 1

        

        # Sleep to maintain 1000 messages per second
        elapsed_time = time.time() - start_time
        time_to_sleep = max(0, (1 - elapsed_time))  # Ensure we don't sleep negative time
        time.sleep(time_to_sleep)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    # Stop the loop and disconnect
    client.loop_stop()
    client.disconnect()
