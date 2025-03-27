import paho.mqtt.client as mqtt

# MQTT broker details
broker = "172.18.213.137"
port = 1883
topic = "MON"
message = "Hello, MQTT from Python!"

# Create an MQTT client instance
client = mqtt.Client()

# Connect to the MQTT broker
client.connect(broker, port, 60)

# Publish a message to the topic
client.publish(topic, message)

print(f"Published message: '{message}' to topic: '{topic}'")

# Disconnect from the broker
client.disconnect()
