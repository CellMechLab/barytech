from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from app.models import Base, DeviceData, ClientSession, IoTDevice
from datetime import datetime
from fastapi import HTTPException
from contextlib import asynccontextmanager
import logging
from sqlalchemy import insert
import pandas as pd

logging.basicConfig(level=logging.DEBUG)
# SQLite async database URL (you can use other databases like PostgreSQL or MySQL)
DATABASE_URL = "postgresql+asyncpg://postgres:calculator1@localhost:5432/schaefer"

# Create an async engine
async_engine = create_async_engine(
    DATABASE_URL, 
    echo=True, 
    pool_size=20,         # Maximum number of connections in the pool
    max_overflow=40,      # Number of extra connections allowed
    pool_timeout=60,      # Timeout (in seconds) to acquire a connection
    )

# Create an async session factory
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)



@asynccontextmanager
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# Create tables asynchronously
async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Validate device
async def validate_device(db: AsyncSession, device_id: str, device_token: str):
    """
    Validate if the device_id and device_token pair is valid.
    """
    print("validate", device_id, device_token)
    result = await db.execute(
        select(IoTDevice).where(IoTDevice.id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device.device_token != device_token:
        raise HTTPException(status_code=403, detail="Invalid device token")

    return device

# Save device data
async def save_device_data_batch(
    db: AsyncSession, 
    device_data_list: list
):
    """
    Save a batch of device data entries.
    """
    if not device_data_list:
        return

    try:
        # Convert data to ORM objects
        # db_data_list = [
        #     DeviceData(
        #         device_id=data["device_id"],
        #         timestamp=datetime.fromisoformat(data["timestamp"]),  # Ensure ISO 8601 format
        #         displacement=data["displacement"],
        #         force=data["force"],
        #     )
        #     for data in device_data_list
        # ]

        # Add all data in one batch
        print("Inserting %d records using bulk insert.", len(device_data_list))
        stmt = insert(DeviceData).values(device_data_list)
        try:
        # Execute the bulk insert
            await db.execute(stmt)
            await db.commit()
            print("Bulk insert of %d records committed successfully.", len(device_data_list))
        except Exception as e:
            await db.rollback()
            print("Error performing bulk insert: %s", e)
            raise ValueError(f"Error saving batch: {str(e)}")

    except ValueError as e:
        raise ValueError(f"Error saving batch: {str(e)}")


# Get device data by device_id
async def get_device_data_by_device_id(db: AsyncSession, device_id: str):
    """Retrieve all data for a specific device."""
    result = await db.execute(
        select(DeviceData).where(DeviceData.device_id == device_id)
    )
    return result.scalars().all()

# Save or update a client session
async def save_client_session(db: AsyncSession, client_id: int, websocket_id: str):
    """Save or update a client session."""
    result = await db.execute(
        select(ClientSession).where(ClientSession.client_id == str(client_id))
    )
    session = result.scalars().first()
    if session:
        session.websocket_id = websocket_id
        session.connected = True
    else:
        session = ClientSession(client_id=client_id, websocket_id=websocket_id)
    db.add(session)
    await db.commit()

# Mark client as disconnected
async def mark_client_disconnected(db: AsyncSession, client_id: str):
    """Mark a client as disconnected."""
    result = await db.execute(
        select(ClientSession).where(ClientSession.client_id == str(client_id))
    )
    session = result.scalars().first()
    if session:
        session.connected = False
        await db.commit()

# Get connected clients
async def get_connected_clients(db: AsyncSession):
    """Retrieve all connected clients from the client_sessions table."""
    result = await db.execute(
        select(ClientSession.client_id).where(ClientSession.connected == True)
    )
    return result.scalars().all()

async def get_user_id_by_device_id(db, device_id: str) -> str:
    result = await db.execute(select(IoTDevice.user_id).where(IoTDevice.id == device_id))
    user_id = result.scalar()
    if not user_id:
        raise ValueError(f"No user found for given device_id: {device_id}")
    return user_id


import os
import h5py
import numpy as np

async def export_device_data_to_hdf5(file_path: str = "data/device_data.hdf5"):
    """Export DeviceData to an HDF5 file with curve0/segment0/Force,Z structure."""
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(DeviceData))
        data = result.scalars().all()

        if not data:
            print("No data found in device_data table.")
            raise HTTPException(status_code=404, detail="No device data available to export.")

        # Convert SQLAlchemy objects to list of dicts
        records = [d.__dict__ for d in data]
        for record in records:
            record.pop('_sa_instance_state', None)

        # Collect force and z values for a single curve
        force_values = []
        z_values = []
        for record in records:
            force = record.get("force", None)  # Adjust field name if different
            z = record.get("displacement", None)  # Adjust field name if different
            if force is not None and z is not None:  # Skip invalid records
                force_values.append(force)
                z_values.append(z)

        if not force_values or not z_values:
            print("No valid force or z data found.")
            raise HTTPException(status_code=400, detail="No valid force or z data to export.")

        # Create HDF5 file
        with h5py.File(file_path, "w") as f:
            # Create curve0 group
            curve_group = f.create_group("curve0")
            # Create segment0 group
            segment_group = curve_group.create_group("segment0")
            # Create Force and Z datasets
            segment_group.create_dataset("Force", data=np.array(force_values, dtype=float))
            segment_group.create_dataset("Z", data=np.array(z_values, dtype=float))

        print(f"Exported {len(force_values)} records to {file_path}")
