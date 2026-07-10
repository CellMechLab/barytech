from sqlalchemy import Column, Integer, String, JSON, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from app.utils import generate_token  # Utility function to generate token
from sqlalchemy.orm import relationship
from sqlalchemy import select

Base = declarative_base()


class Folder(Base):
    """Named container that groups one or more measurement curves for a user."""
    __tablename__ = "folders"

    # Auto-incrementing primary key for the folder row.
    id = Column(Integer, primary_key=True, index=True)
    # Human-readable label set by the user, e.g. "Collagen A 2026-06-18".
    name = Column(String, nullable=False)
    # Foreign key linking the folder to its owning user account.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # UTC timestamp recorded when the folder was first created.
    created_at = Column(DateTime, default=datetime.utcnow)
    # Experiment-wide metadata shared by all curves in this folder (HDF5 tip export).
    velocity = Column(Float, nullable=True)
    force_conversion_factor = Column(Float, nullable=True)
    z_conversion_factor = Column(Float, nullable=True)
    spring_constant = Column(Float, nullable=True)
    tip_geometry = Column(String, nullable=True)
    tip_radius = Column(Float, nullable=True)
    # Tip half-angle in degrees (cone/pyramid geometries).
    tip_angle = Column(Float, nullable=True)
    sampling_rate = Column(Float, nullable=True)
    # Force sensor model used for this experiment, e.g. Aurora, CSense.
    sensor_type = Column(String, nullable=True)

    # ORM back-reference to the owning User row.
    user = relationship("User", back_populates="folders")
    # All device_data rows that belong to this folder; deleted when folder is removed.
    device_data = relationship("DeviceData", back_populates="folder", cascade="all, delete-orphan")


class DeviceData(Base):
    __tablename__ = "device_data"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("iot_devices.id"), nullable=False, index=True)  # Foreign key to IoTDevice
    timestamp = Column(DateTime, default=datetime.utcnow)  # Time the data was recorded
    displacement = Column(Float, nullable=False)  # Displacement in micrometers (µm)
    force = Column(Float, nullable=False)  # Force in micronewtons (µN)
    # Foreign key to the folder this row belongs to; nullable for un-grouped rows.
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True)
    # Zero-based index of the save-cycle (ON→OFF) within the folder this row was recorded during.
    curve_index = Column(Integer, default=0, nullable=False)
    # Indentation phase: 0 = approaching/indenting (segment0), 1 = retracting (segment1).
    phase = Column(Integer, default=0, nullable=False)
    # Motor activity flag from device telemetry: 0 = idle, 1 = moving.
    motor_working = Column(Integer, default=0, nullable=False)

    # Relationship with IoTDevice
    device = relationship("IoTDevice", back_populates="data")
    # ORM back-reference to the parent Folder row.
    folder = relationship("Folder", back_populates="device_data")


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
    # Relationship to Folder — all folders owned by this user.
    folders = relationship("Folder", back_populates="user")

    

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


