"""API routes for device CRUD operations, telemetry access, data export, and folder management."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import (
    IoTDeviceCreate, IoTDeviceResponse, DeviceDataResponse,
    FolderCreate, FolderResponse, CurveInfo,
    DeviceDataRowResponse, GroupedCurveResponse, GroupedFolderResponse,
)
from app.models import IoTDevice, DeviceData, Folder
from app.db import get_db
from app.utils import generate_token
from app.auth import get_current_user_id  # Dependency to get user_id from token
from typing import List
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import func
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


@router.get("/device-data-grouped/", response_model=List[GroupedFolderResponse])
async def get_device_data_grouped(
    user_id: int = Depends(get_current_user_id),
):
    """
    Return device_data pre-grouped into a 3-level hierarchy:
    Folder → Curve (save-cycle) → Data rows.

    Rows with no folder_id are collected into a synthetic "No folder" bucket
    which is always placed last in the list.
    Folders are ordered most-recently-created first.
    Curves within each folder are ordered by curve_index ascending.
    Rows within each curve are ordered by timestamp ascending.
    """
    async with get_db() as db:
        # Single query: join device_data → iot_devices (for user scope) →
        # left-join folders (so null-folder rows are included).
        result = await db.execute(
            select(DeviceData, Folder)
            .join(IoTDevice, IoTDevice.id == DeviceData.device_id)
            .outerjoin(Folder, Folder.id == DeviceData.folder_id)
            .filter(IoTDevice.user_id == user_id)
            # Pre-sort by curve_index then timestamp; folder ordering is done in Python
            # to handle NULL folder_id cleanly without dialect-specific NULLS LAST.
            .order_by(DeviceData.curve_index.asc(), DeviceData.timestamp.asc())
        )
        pairs = result.all()

    # ── Group in Python ───────────────────────────────────────────────────────
    # folder_map  : folder_id (or None) → folder bucket dict
    # folder_order: insertion-ordered list of folder_ids to preserve first-seen order
    folder_map: dict = {}
    folder_order: list = []

    for data_row, folder_row in pairs:
        # Use Python None as the dict key for null-folder rows.
        fid = data_row.folder_id

        if fid not in folder_map:
            folder_map[fid] = {
                "folder_id": fid,
                "folder_name": folder_row.name if folder_row is not None else "No folder",
                "folder_created_at": folder_row.created_at if folder_row is not None else None,
                # Maps curve_index → list of DeviceData rows for that curve.
                "curve_map": {},
            }
            folder_order.append(fid)

        # Treat NULL curve_index as 0 to avoid key collisions.
        ci = data_row.curve_index if data_row.curve_index is not None else 0
        if ci not in folder_map[fid]["curve_map"]:
            folder_map[fid]["curve_map"][ci] = []
        folder_map[fid]["curve_map"][ci].append(data_row)

    # ── Sort folders: most-recent first, null-folder always last ─────────────
    def _folder_sort_key(fid):
        """(null_flag, -timestamp) so real folders sort newest-first, None last."""
        created_at = folder_map[fid]["folder_created_at"]
        if created_at is None:
            # Ensure None-folder sorts after all real folders regardless of timestamp.
            return (1, 0)
        return (0, -created_at.timestamp())

    sorted_fids = sorted(folder_order, key=_folder_sort_key)

    # ── Build response objects ────────────────────────────────────────────────
    response: list = []
    for fid in sorted_fids:
        fd = folder_map[fid]

        curves = [
            GroupedCurveResponse(
                curve_index=ci,
                row_count=len(rows),
                rows=[
                    DeviceDataRowResponse(
                        id=r.id,
                        device_id=r.device_id,
                        timestamp=r.timestamp,
                        displacement=r.displacement,
                        force=r.force,
                        folder_id=r.folder_id,
                        curve_index=r.curve_index if r.curve_index is not None else 0,
                    )
                    for r in rows
                ],
            )
            # Sort curves by index ascending within each folder.
            for ci, rows in sorted(fd["curve_map"].items())
        ]

        response.append(
            GroupedFolderResponse(
                folder_id=fd["folder_id"],
                folder_name=fd["folder_name"],
                folder_created_at=fd["folder_created_at"],
                curves=curves,
            )
        )

    return response


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
from app.db import export_device_data_to_hdf5, export_folder_to_hdf5

# ── Legacy single-curve export (kept for backward compatibility) ──────────────

@router.get("/export/device_data")
async def download_device_data(
    # Restricts export to data owned by the authenticated user only.
    user_id: int = Depends(get_current_user_id),
):
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
    await export_device_data_to_hdf5(file_path, user_id)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Export failed")

    return FileResponse(
        path=file_path,
        filename=export_filename,
        media_type="application/octet-stream"
    )


# ── Folder management routes ──────────────────────────────────────────────────

@router.post("/folders/", response_model=FolderResponse, status_code=201)
async def create_folder(
    payload: FolderCreate,
    user_id: int = Depends(get_current_user_id),
):
    """Create a new measurement folder for the authenticated user."""
    async with get_db() as db:
        # Build the new folder row and associate it with the requesting user.
        new_folder = Folder(name=payload.name, user_id=user_id)
        db.add(new_folder)
        # Prevent crash if the DB write fails (e.g. unique constraint violation).
        try:
            await db.commit()
            await db.refresh(new_folder)
        except Exception as exc:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create folder: {exc}")

        # New folder has no curves or rows yet.
        response = FolderResponse(
            id=new_folder.id,
            name=new_folder.name,
            created_at=new_folder.created_at,
            curve_count=0,
            row_count=0,
        )
        return response


@router.get("/folders/", response_model=List[FolderResponse])
async def list_folders(
    user_id: int = Depends(get_current_user_id),
):
    """List all folders owned by the current user with curve and row counts."""
    async with get_db() as db:
        # Fetch folders with aggregated curve_count and row_count in one query.
        result = await db.execute(
            select(
                Folder,
                # Count distinct curve indices to get the number of curves per folder.
                func.count(DeviceData.curve_index.distinct()).label("curve_count"),
                # Count total rows stored in this folder.
                func.count(DeviceData.id).label("row_count"),
            )
            .outerjoin(DeviceData, DeviceData.folder_id == Folder.id)
            .where(Folder.user_id == user_id)
            .group_by(Folder.id)
            .order_by(Folder.created_at.desc())
        )
        rows = result.all()

        folders = []
        for folder, curve_count, row_count in rows:
            folders.append(
                FolderResponse(
                    id=folder.id,
                    name=folder.name,
                    created_at=folder.created_at,
                    curve_count=curve_count,
                    row_count=row_count,
                )
            )
        return folders


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """Delete a folder and all its device_data rows (cascade)."""
    async with get_db() as db:
        result = await db.execute(
            select(Folder).where(Folder.id == folder_id, Folder.user_id == user_id)
        )
        folder = result.scalars().first()

        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found or not authorized.")

        # Cascade delete is handled by the ORM relationship definition.
        await db.delete(folder)
        # Prevent crash if the delete fails (e.g. FK constraint from other tables).
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to delete folder: {exc}")

        return {"detail": f"Folder {folder_id} and all its data deleted successfully."}


@router.get("/folders/{folder_id}/curves", response_model=List[CurveInfo])
async def list_folder_curves(
    folder_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """Return one summary entry per curve stored in the given folder."""
    async with get_db() as db:
        # Verify the folder belongs to the requesting user before exposing data.
        folder_result = await db.execute(
            select(Folder).where(Folder.id == folder_id, Folder.user_id == user_id)
        )
        if not folder_result.scalars().first():
            raise HTTPException(status_code=404, detail="Folder not found or not authorized.")

        # Aggregate row count per curve_index.
        result = await db.execute(
            select(
                DeviceData.curve_index,
                func.count(DeviceData.id).label("row_count"),
            )
            .where(DeviceData.folder_id == folder_id)
            .group_by(DeviceData.curve_index)
            .order_by(DeviceData.curve_index)
        )
        rows = result.all()

        return [CurveInfo(curve_index=row.curve_index, row_count=row.row_count) for row in rows]


# ── Folder HDF5 export ────────────────────────────────────────────────────────

@router.get("/export/folder/{folder_id}")
async def download_folder_hdf5(
    folder_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """Export all curves in a folder to a single HDF5 file named after the folder."""
    # Preferred persistent export directory; fall back to project-local path if read-only.
    preferred_export_directory_path = "/data/barytech"
    fallback_export_directory_path = os.path.join(os.getcwd(), "data", "barytech")
    # Resolve the export directory, falling back if the preferred path is not writable.
    export_directory_path = preferred_export_directory_path
    # Prevent crash when deployment filesystem blocks writes to `/data`.
    try:
        os.makedirs(preferred_export_directory_path, exist_ok=True)
    except OSError:
        export_directory_path = fallback_export_directory_path
        os.makedirs(export_directory_path, exist_ok=True)

    # Fetch the folder name to use as the filename.
    async with get_db() as db:
        folder_result = await db.execute(
            select(Folder).where(Folder.id == folder_id, Folder.user_id == user_id)
        )
        folder = folder_result.scalars().first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found or not authorized.")
        # Sanitise the folder name so it is safe to use as a filesystem filename.
        safe_name = "".join(c if c.isalnum() or c in " _-." else "_" for c in folder.name).strip()
        # Append a timestamp so repeated exports never overwrite each other.
        export_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        export_filename = f"{safe_name}_{export_timestamp}.hdf5"

    # Builds the absolute export file path.
    file_path = os.path.join(export_directory_path, export_filename)
    await export_folder_to_hdf5(file_path, folder_id, user_id)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Export failed — file not created.")

    return FileResponse(
        path=file_path,
        filename=export_filename,
        media_type="application/octet-stream",
    )
