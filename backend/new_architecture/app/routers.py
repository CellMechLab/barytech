"""API routes for device CRUD operations, telemetry access, and data export."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import IoTDeviceCreate, IoTDeviceResponse, DeviceDataResponse
from app.models import IoTDevice, DeviceData
from app.db import get_db
from app.utils import generate_token
from app.auth import get_current_user_id  # Dependency to get user_id from token
from typing import List
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from pydantic import BaseModel

router = APIRouter()


@router.post("/devices/", response_model=IoTDeviceResponse)
async def create_device(
    device: IoTDeviceCreate,
    user_id: int = Depends(get_current_user_id),  # Extract user_id from the token
):
    async with get_db() as db:  # Use async context manager for database session
        print("Received request")

        # Generate a unique token for the device
        device_data = device.dict(exclude={"device_token"})
        device_data["device_token"] = generate_token(16)  # Generate a 16-character token

        # Set the user_id and default status
        device_data["user_id"] = user_id  # Associate with logged-in user
        device_data["status"] = "Offline"

        # Save the device to the database
        try:
            new_device = IoTDevice(**device_data)
            db.add(new_device)
            print("Device added to session")
            await db.commit()
            print("Device committed to database")
            await db.refresh(new_device)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save device: {str(e)}")

        return new_device


@router.get("/device-data/", response_model=List[DeviceDataResponse])
async def get_device_data(
    user_id: int = Depends(get_current_user_id),  # Ensure only the user's data is fetched
):
    async with get_db() as db:
        # Join DeviceData with IoTDevice and filter by user_id
        result = await db.execute(
            select(DeviceData)
            .join(IoTDevice)
            .filter(IoTDevice.user_id == user_id)
            .options(joinedload(DeviceData.device))  # Optional: Load device relationship
        )
        data = result.scalars().all()
        return data


@router.get("/devices/", response_model=List[IoTDeviceResponse])
async def get_devices(
    user_id: int = Depends(get_current_user_id),  # Ensure devices are filtered by the logged-in user
):
    async with get_db() as db:
        result = await db.execute(
            select(IoTDevice).filter(IoTDevice.user_id == user_id)
        )
        devices = result.scalars().all()
        return devices


class DeviceDeleteRequest(BaseModel):
    device_ids: List[str]  # Expecting a list of strings


@router.delete("/devices/")
async def delete_devices(
    request: DeviceDeleteRequest,  # Use the Pydantic model here
    user_id: int = Depends(get_current_user_id),
):
    async with get_db() as db:
        device_ids = request.device_ids  # Access the list of device IDs
        if not device_ids:
            raise HTTPException(status_code=400, detail="No device IDs provided.")

        # Perform the deletion logic
        result = await db.execute(
            select(IoTDevice).filter(
                IoTDevice.id.in_(device_ids), IoTDevice.user_id == user_id
            )
        )
        devices = result.scalars().all()

        if not devices:
            raise HTTPException(
                status_code=404, detail="Devices not found or not authorized."
            )

        for device in devices:
            await db.delete(device)
        await db.commit()

        return {"detail": f"{len(devices)} devices deleted successfully."}


class DeviceDataDeleteRequest(BaseModel):
    ids: List[int]  # Expecting a list of strings


@router.delete("/device-data/")
async def delete_device_data(
    request: DeviceDataDeleteRequest,  # Pydantic model with `device_ids`
    user_id: int = Depends(get_current_user_id),
):
    async with get_db() as db:
        ids = request.ids
        if not ids:
            raise HTTPException(status_code=400, detail="No device data IDs provided.")

        # Perform the deletion logic
        result = await db.execute(
            select(DeviceData)
            .join(IoTDevice, IoTDevice.id == DeviceData.device_id)
            .filter(DeviceData.id.in_(ids), IoTDevice.user_id == user_id)
        )
        device_data_entries = result.scalars().all()

        if not device_data_entries:
            raise HTTPException(
                status_code=404,
                detail="Device data entries not found or not authorized.",
            )

        for entry in device_data_entries:
            await db.delete(entry)
        await db.commit()

        return {"detail": f"{len(device_data_entries)} device data entries deleted successfully."}


from fastapi.responses import FileResponse
import os
from datetime import datetime
from app.db import export_device_data_to_hdf5  

@router.get("/export/device_data")
async def download_device_data():
    # Defines the preferred absolute directory for exported HDF5 files.
    preferred_export_directory_path = "/data/barytech"
    # Defines a writable project-local fallback when `/data` is read-only.
    fallback_export_directory_path = os.path.join(os.getcwd(), "data", "barytech")
    # Stores the resolved export directory chosen for this request.
    export_directory_path = preferred_export_directory_path
    # Prevent crash when deployment filesystem blocks writes to `/data`.
    try:
        os.makedirs(preferred_export_directory_path, exist_ok=True)
    except OSError:
        export_directory_path = fallback_export_directory_path
        os.makedirs(export_directory_path, exist_ok=True)
    # Generates a timestamp suffix for chronological and unique export filenames.
    export_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    # Defines the download filename for this specific export request.
    export_filename = f"device_data_{export_timestamp}.hdf5"
    # Builds the absolute export file path with the required .hdf5 extension.
    file_path = os.path.join(export_directory_path, export_filename)
    await export_device_data_to_hdf5(file_path)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Export failed")

    return FileResponse(
        path=file_path,
        filename=export_filename,
        media_type="application/octet-stream"
    )
