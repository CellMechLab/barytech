from sqlalchemy import Column, Integer, String, JSON, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from app.utils import generate_token  # Utility function to generate token
from sqlalchemy.orm import relationship
from sqlalchemy import select

Base = declarative_base()

class DeviceData(Base):
    __tablename__ = "device_data"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("iot_devices.id"), nullable=False, index=True)  # Foreign key to IoTDevice
    timestamp = Column(DateTime, default=datetime.utcnow)  # Time the data was recorded
    displacement = Column(Float, nullable=False)  # Displacement data
    force = Column(Float, nullable=False)  # Force data

    # Relationship with IoTDevice
    device = relationship("IoTDevice", back_populates="data")


class ClientSession(Base):
    __tablename__ = "client_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String, unique=True, index=True)  # Client ID to track individual sessions
    websocket_id = Column(String)  # WebSocket ID (optional) to track connection details
    connected = Column(Boolean, default=True)  # Whether the client is currently connected
    last_connected_at = Column(DateTime, default=datetime.utcnow)  # Timestamp for last connection

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    # Relationship to IoTDevice
    devices = relationship("IoTDevice", back_populates="user")

    

class IoTDevice(Base):
    __tablename__ = "iot_devices"
    
    id = Column(String, primary_key=True, default=lambda: generate_token(12), index=True)  # String-based ID
    device_name = Column(String, nullable=False, index=True)
    device_type = Column(String, nullable=False)
    status = Column(String, default="Offline")
    created_at = Column(DateTime, default=datetime.utcnow)
    device_token = Column(String, unique=True, default=lambda: generate_token(16), nullable=False)  # Unique token

    # Foreign key to the User table
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Make nullable=True temporarily

    # Relationship for ORM
    user = relationship("User", back_populates="devices")
    
    data = relationship("DeviceData", back_populates="device", cascade="all, delete-orphan")  # Updated relationship


