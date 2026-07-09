"""Database access layer for async SQLAlchemy sessions and persistence helpers."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from app.models import Base, DeviceData, ClientSession, IoTDevice, Folder
from app.config import settings
from datetime import datetime
from fastapi import HTTPException
from contextlib import asynccontextmanager
import logging
from sqlalchemy import insert
import pandas as pd

logging.basicConfig(level=logging.DEBUG)
# Stores the runtime database URL loaded from environment settings.
DATABASE_URL = settings.DATABASE_URL
# Stores database URL rewritten to use async SQLAlchemy drivers when needed.
normalized_database_url = DATABASE_URL

# Convert sync SQLite URL to async SQLite driver required by SQLAlchemy asyncio.
if DATABASE_URL.startswith("sqlite:///"):
    normalized_database_url = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
# Convert sqlite URL variant without triple slash to async driver variant.
elif DATABASE_URL.startswith("sqlite://"):
    normalized_database_url = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)

# Holds common async engine options used across all supported database backends.
engine_options = {
    "echo": True,
}

# Apply connection pool tuning only for network database backends.
if not normalized_database_url.startswith("sqlite+aiosqlite://"):
    engine_options.update({
        "pool_size": 20,         # Maximum number of connections in the pool
        "max_overflow": 40,      # Number of extra connections allowed
        "pool_timeout": 60,      # Timeout (in seconds) to acquire a connection
    })

# Create an async engine
async_engine = create_async_engine(
    normalized_database_url,
    **engine_options,
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
async def save_client_session(db: AsyncSession, client_id: str, websocket_id: str):
    """Save or update a client session."""
    result = await db.execute(
        select(ClientSession).where(ClientSession.client_id == client_id)
    )
    session = result.scalars().first()
    if session:
        session.websocket_id = websocket_id
        session.connected = True
        session.last_connected_at = datetime.utcnow()
    else:
        session = ClientSession(client_id=client_id, websocket_id=websocket_id)
    db.add(session)
    await db.commit()

# Mark client as disconnected
async def mark_client_disconnected(db: AsyncSession, client_id: str):
    """Mark a client as disconnected."""
    result = await db.execute(
        select(ClientSession).where(ClientSession.client_id == client_id)
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

# Default experiment metadata written to HDF5 tip groups when folder values are unset.
EXPERIMENT_METADATA_DEFAULTS = {
    "velocity": 1e-6,
    "force_conversion_factor": 1.0,
    "z_conversion_factor": 1.0,
    "spring_constant": 0.1,
    "tip_geometry": "sphere",
    "tip_radius": 1e-5,
    "sampling_rate": 1e5,
}


def _to_float_or_none(value):
    """Coerce a DB value to float; returns None when conversion fails."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _export_force_value(raw_force):
    """Negate force for HDF5 export; legacy rows may still store force as strings."""
    force = _to_float_or_none(raw_force)
    if force is None:
        return None
    return -force

async def export_device_data_to_hdf5(file_path: str = "data/device_data.hdf5", user_id: int = None):
    """Export DeviceData to an HDF5 file with curve0/segment0/Force,Z structure.

    When user_id is provided only rows whose parent IoTDevice belongs to that
    user are included, preventing cross-user data leakage in the export.
    """
    # Resolves the destination directory from the provided export path.
    export_directory_path = os.path.dirname(file_path) or "."
    # Ensures the destination directory exists before writing the HDF5 file.
    os.makedirs(export_directory_path, exist_ok=True)

    async with AsyncSessionLocal() as session:
        # Build a query that joins DeviceData -> IoTDevice so we can filter by owner.
        query = select(DeviceData).join(IoTDevice, IoTDevice.id == DeviceData.device_id)
        # Apply user scope when a user_id is supplied; omit to export all rows.
        if user_id is not None:
            query = query.filter(IoTDevice.user_id == user_id)
        result = await session.execute(query)
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
            force = _export_force_value(record.get("force"))
            z = _to_float_or_none(record.get("displacement"))
            if force is not None and z is not None:
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

        # Logs the absolute output location to simplify export-path debugging.
        resolved_output_file_path = os.path.abspath(file_path)
        print(f"Exported {len(force_values)} records to {resolved_output_file_path}")


async def upsert_folder_metadata(
    db: AsyncSession,
    folder_id: int,
    metadata: dict,
):
    """Update experiment-wide metadata on a folder (shared by all curves in export)."""
    if not metadata or folder_id is None:
        return

    # Maps incoming payload keys to Folder metadata column names.
    field_map = {
        "velocity": "velocity",
        "force_conversion_factor": "force_conversion_factor",
        "force_scale_to_n": "force_conversion_factor",
        "conversion_factor": "force_conversion_factor",
        "z_conversion_factor": "z_conversion_factor",
        "z_scale_to_m": "z_conversion_factor",
        "spring_constant": "spring_constant",
        "tip_geometry": "tip_geometry",
        "tip_radius": "tip_radius",
        "sampling_rate": "sampling_rate",
    }
    updates = {}
    for source_key, column_name in field_map.items():
        value = metadata.get(source_key)
        if value is not None:
            updates[column_name] = value

    if not updates:
        return

    result = await db.execute(select(Folder).where(Folder.id == folder_id))
    folder = result.scalars().first()
    if not folder:
        return

    for key, value in updates.items():
        setattr(folder, key, value)

    # Prevent crash if metadata upsert fails while telemetry rows still save.
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        print(f"Error upserting folder metadata: {exc}")


def _resolve_folder_metadata_value(folder: Folder, field: str):
    """Return folder metadata value or the configured default for HDF5 export."""
    folder_value = getattr(folder, field, None)
    if folder_value is not None:
        return folder_value
    return EXPERIMENT_METADATA_DEFAULTS[field]


def get_folder_export_metadata(folder: Folder) -> dict:
    """Return resolved metadata values that will be written to every HDF5 tip group."""
    return {
        "velocity": float(_resolve_folder_metadata_value(folder, "velocity")),
        "force_conversion_factor": float(
            _resolve_folder_metadata_value(folder, "force_conversion_factor")
        ),
        "z_conversion_factor": float(
            _resolve_folder_metadata_value(folder, "z_conversion_factor")
        ),
        "spring_constant": float(_resolve_folder_metadata_value(folder, "spring_constant")),
        "tip_geometry": str(_resolve_folder_metadata_value(folder, "tip_geometry")),
        "tip_radius": float(_resolve_folder_metadata_value(folder, "tip_radius")),
        "sampling_rate": float(_resolve_folder_metadata_value(folder, "sampling_rate")),
    }


def _write_tip_metadata_group(tip_group, folder: Folder):
    """Write shared experiment metadata into an HDF5 tip group for one curve."""
    tip_group.attrs["velocity"] = float(_resolve_folder_metadata_value(folder, "velocity"))
    tip_group.attrs["force_scale_to_n"] = float(
        _resolve_folder_metadata_value(folder, "force_conversion_factor")
    )
    tip_group.attrs["z_scale_to_m"] = float(
        _resolve_folder_metadata_value(folder, "z_conversion_factor")
    )
    tip_group.attrs["spring_constant"] = float(
        _resolve_folder_metadata_value(folder, "spring_constant")
    )
    tip_group.attrs["sampling_rate"] = float(
        _resolve_folder_metadata_value(folder, "sampling_rate")
    )
    tip_group.attrs["geometry"] = str(_resolve_folder_metadata_value(folder, "tip_geometry"))
    tip_group.attrs["parameter"] = "Radius"
    tip_group.attrs["unit"] = "um"
    tip_group.attrs["value"] = float(_resolve_folder_metadata_value(folder, "tip_radius"))


async def export_folder_to_hdf5(file_path: str, folder_id: int, user_id: int) -> str:
    """Export all curves in a folder to a single HDF5 file.

    The file is structured as:
        curve0/segment0/Force   — indent phase (phase=0)
        curve0/segment0/Z
        curve0/segment1/Force   — retract phase (phase=1)
        curve0/segment1/Z
        curve0/tip              — shared experiment metadata from folder
        curve1/…
        …

    Rows are queried from device_data filtered by folder_id and ordered by
    curve_index then timestamp so each curve is written in chronological order.
    Returns the resolved absolute path of the written file.
    """
    # Resolve and create the output directory before any DB work.
    export_directory_path = os.path.dirname(file_path) or "."
    os.makedirs(export_directory_path, exist_ok=True)

    async with AsyncSessionLocal() as session:
        # Verify that the folder exists and belongs to the requesting user.
        folder_result = await session.execute(
            select(Folder).where(Folder.id == folder_id, Folder.user_id == user_id)
        )
        folder = folder_result.scalars().first()
        if not folder:
            # Prevent leaking data from other users or non-existent folders.
            raise HTTPException(status_code=404, detail="Folder not found or not authorized.")

        # Fetch all device_data rows for this folder ordered for deterministic curve output.
        data_result = await session.execute(
            select(DeviceData)
            .where(DeviceData.folder_id == folder_id)
            .order_by(DeviceData.curve_index, DeviceData.timestamp)
        )
        rows = data_result.scalars().all()

        if not rows:
            # 400, not 404 — the folder exists but contains no recorded device_data yet.
            raise HTTPException(status_code=400, detail="This folder has no recorded data yet. Start a save session with this folder selected first.")

        # Group rows by curve_index, then split each curve by phase (segment0/segment1).
        curves: dict = {}
        for row in rows:
            idx = row.curve_index if row.curve_index is not None else 0
            if idx not in curves:
                curves[idx] = {
                    "segment0": {"force": [], "z": []},
                    "segment1": {"force": [], "z": []},
                }
            # phase 0 → segment0 (indent), phase 1 → segment1 (retract).
            phase = row.phase if row.phase in (0, 1) else 0
            segment_key = "segment0" if phase == 0 else "segment1"
            force = _export_force_value(row.force)
            z = _to_float_or_none(row.displacement)
            if force is None or z is None:
                continue
            curves[idx][segment_key]["force"].append(force)
            curves[idx][segment_key]["z"].append(z)

        total_rows = sum(
            len(curve_data["segment0"]["force"]) + len(curve_data["segment1"]["force"])
            for curve_data in curves.values()
        )
        if total_rows == 0:
            raise HTTPException(
                status_code=400,
                detail="No valid force or displacement data to export in this folder.",
            )

        # Write the HDF5 file with one group per curve.
        with h5py.File(file_path, "w") as hdf:
            for curve_idx in sorted(curves.keys()):
                curve_group = hdf.create_group(f"curve{curve_idx}")
                curve_data = curves[curve_idx]

                for segment_name in ("segment0", "segment1"):
                    segment_values = curve_data[segment_name]
                    if not segment_values["force"]:
                        continue
                    segment_group = curve_group.create_group(segment_name)
                    segment_group.create_dataset(
                        "Force",
                        data=np.array(segment_values["force"], dtype=float),
                    )
                    segment_group.create_dataset(
                        "Z",
                        data=np.array(segment_values["z"], dtype=float),
                    )

                # Same experiment metadata on every curve in this folder export.
                tip_group = curve_group.create_group("tip")
                _write_tip_metadata_group(tip_group, folder)

        resolved_path = os.path.abspath(file_path)
        print(
            f"Folder export: {len(curves)} curve(s), {total_rows} rows → {resolved_path}"
        )
        return resolved_path
