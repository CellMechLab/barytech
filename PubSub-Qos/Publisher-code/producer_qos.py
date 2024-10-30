import json
import paho.mqtt.client as mqtt
import time

client = mqtt.Client()
client.connect("192.168.5.2", 1883, 60)


client.loop_start()

def publish_messages():
    start_time = time.time()
    num_messages = 10000  
    sent_count = 0

    for i in range(num_messages):
        current_time = time.time()

        
        message = {
            "msg_id": i,  
            "sample": f"sample {i}",
            "timestamp": current_time
        }
        client.publish("test/topic", json.dumps(message), qos=1)
        sent_count += 1
        time.sleep(0.001)  

    end_time = time.time()
    print(f"Sent {sent_count} messages in {end_time - start_time} seconds.")

publish_messages()

client.loop_stop()

