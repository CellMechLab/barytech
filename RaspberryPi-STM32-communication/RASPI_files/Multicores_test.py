import spidev
import time
import multiprocessing
import paho.mqtt.client as mqtt

#MQTT broker
BROKER = "192.168.5.2"  
PORT = 1883
TOPIC = "adc/data"

# SPI Setup
spi = spidev.SpiDev()
spi.open(0, 0)  # Open SPI bus 0, device 0
spi.max_speed_hz = 500000  # Adjust as needed

def read_spi():
                                 #Receives raw SPI data from STM32
    response = spi.readbytes(3)  # Expecting 3 bytes
    adc_value = (response[0] << 16) | (response[1] << 8) | response[2]
    return adc_value

def core_1(buffer):
                     #"Offline buffer that stores ADC data
    while True:
        adc_value = read_spi()
        print(f"Core 1 - Received Sensor Readings: {adc_value}")
        buffer.put(adc_value)  # Store data in the queue (buffer)
        time.sleep(1)  # Adjust the delay based on your needs

def on_connect(client, userdata, flags, rc):
    
    print(f"Connected to MQTT Broker with result code {rc}")

def on_publish(client, userdata, mid):
    
    print(f"Message {mid} published")

def core_2(buffer):
                             #Producer that sends data to MQTT broker
    client = mqtt.Client()  # Create a new MQTT client
    client.on_connect = on_connect
    client.on_publish = on_publish
    client.connect(BROKER, PORT, 60)  # Connect to the broker

    client.loop_start()  # Start the loop to process MQTT messages
    
    while True:
        if not buffer.empty():
            adc_value = buffer.get()  # Get the latest ADC value from the buffer
            print(f"Core 2 - Sending Sensor Readings to Broker: {adc_value}")
            client.publish(TOPIC, adc_value)  # Send the ADC value to the broker
        time.sleep(1)  # Adjust as needed

if __name__ == "__main__":
    # Create a Queue for communication between Core 1 and Core 2
    buffer = multiprocessing.Queue()

    # Create two processes: Core 1 (offline buffer) and Core 2 (producer to broker)
    process_1 = multiprocessing.Process(target=core_1, args=(buffer,))
    process_2 = multiprocessing.Process(target=core_2, args=(buffer,))

    process_1.start()  # Start Core 1
    process_2.start()  # Start Core 2

    process_1.join()  # Wait for Core 1 to finish
    process_2.join()  # Wait for Core 2 to finish
