This folder contains two subfolders: Publisher-code and Client-code.

The publisher sends messages to a MQTT broker which i had on the same device as my client
and the client then subscribes to receive the incoming messages from the porducer. Both scripts are run on python.
MQTT QOS=1 was set in these scripts to ensure duplicates are received in case of network disruptions.

------------PUBLISHER--------------

To run the publisher:

Open a terminal (or WSL). I used a WSL on my computer to run this.

Navigate to the directory containing the producer_qos.py script.

Run the script using:

	python3 producer_qos.py

NOTE: MAKE SURE TO SET THE CORRECT IP ADDRESS IN THE SCRIPT.

------------CLIENT--------------

To run the client:

Open a terminal. The client and broker were both run on the raspberry pi in my case.

Navigate to the directory containing your client_qos.py script.

Run the script using:

	python3 client_qos.py



------------MQTT BROKER--------------

To start the mosquitto broker:

Run the following command assuming its locally installed on the device.

	sudo systemctl start mosquitto

You can check the status using the command:

	sudo systemctl status mosquitto

