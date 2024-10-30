import paho.mqtt.client as mqtt
import json
import time

received_msg_ids = set()
total_received = 0
duplicate_count = 0
start_time = None
num_messages = 10000  

def on_message(client, userdata, message):
    global total_received, duplicate_count, start_time

    msg = message.payload.decode()
    received_data = json.loads(msg)
    msg_id = received_data['msg_id']
    sent_time = received_data['timestamp']
    received_time = time.time()
    sample = received_data['sample']

   
    if start_time is None:
        start_time = received_time

    
    if msg_id in received_msg_ids:
        duplicate_count += 1
        if duplicate_count <= num_messages:
            print(f"Duplicate received: {msg_id}")
    else:
        received_msg_ids.add(msg_id)
        total_received += 1
    if total_received % 1000 == 0 and total_received <= num_messages:
        elapsed_time = received_time - start_time
        print(f"Processed {total_received} messages in {elapsed_time:.2f} seconds")

    if total_received >= num_messages:
        elapsed_time = received_time - start_time
        print(f"------ Summary ------")
        print(f"Total received: {total_received}")
        print(f"Total duplicates: {duplicate_count}")
        print(f"Elapsed time: {elapsed_time:.2f} seconds")
        print(f"Average message rate: {total_received / elapsed_time:.2f} messages/second")

        
        client.disconnect()


def on_disconnect(client, userdata, rc):
    elapsed_time = time.time() - start_time
    print(f"------ Disconnection Summary -------")
    print(f"Total received: {total_received}")
    print(f"Total duplicates: {duplicate_count}")
    print(f"Elapsed time: {elapsed_time:.2f} seconds")
    print(f"Average message rate: {total_received / elapsed_time:.2f} messages/second")

client = mqtt.Client()
client.on_message = on_message
client.on_disconnect = on_disconnect

client.connect("192.168.5.2", 1883, 60)

client.subscribe("test/topic", qos=1)

client.loop_forever()
