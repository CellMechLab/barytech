from app.db import SessionLocal
from app.models import IoTDevice, DeviceData  # Ensure IoTDevice is correctly imported from your models

# Create a database session
db = SessionLocal()

try:
    # Query all rows from the iot_devices table
    devices = db.query(IoTDevice).all()
    deviceData = db.query(DeviceData).all()

    # Print details of each device
    if devices:
        print("IoT Devices:")
        for device in devices:
            print(
                f"ID: {device.id}, "
                f"Name: {device.device_name}, "
                f"Type: {device.device_type}, "
                f"Status: {device.status}, "
                f"Created At: {device.created_at}, "
                f"Token: {device.device_token}, "
                f"User ID: {device.user_id}"
            )
    else:
        print("No devices found in the database.")
        
    if deviceData:
        print("Device Data:")
        for data in deviceData:
            print(
                f"ID: {data.id}, "
                f"device_id: {device.device_id}, "
            )
    else:
        print("No devices found in the database.")

except Exception as e:
    print(f"Error querying IoT devices: {str(e)}")

finally:
    # Close the database session
    db.close()
