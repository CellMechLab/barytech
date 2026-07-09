from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str


class IoTDeviceCreate(BaseModel):
    device_name: str = Field(..., title="Device Name", description="The name of the IoT device.")
    device_type: str = Field(
        ..., 
        pattern="^(sensor|actuator)$",  # Use `pattern` instead of `regex`
        description="Type of device, must be 'sensor' or 'actuator'."
    )


class IoTDeviceResponse(BaseModel):
    id: str  # Updated to match the `String` type of the SQLAlchemy model
    device_name: str
    device_type: str
    status: str
    device_token: str  # Added the token field
    created_at: datetime = Field(..., description="Time the iot device was created")
    class Config:
        from_attributes = True


class DeviceDataResponse(BaseModel):
    id: int = Field(..., description="Unique identifier for the device data entry")
    device_id: str = Field(..., description="ID of the device associated with this data")
    timestamp: datetime = Field(..., description="Time the data was recorded")
    displacement: float = Field(..., description="Displacement value recorded by the device")
    force: float = Field(..., description="Force value recorded by the device")
    # Indentation phase: 0 = indent, 1 = retract.
    phase: int = 0
    # Motor activity flag: 0 = idle, 1 = moving.
    motor_working: int = 0

    class Config:
        from_attributes = True # Enable ORM mode to work with SQLAlchemy models


class UserResponse(BaseModel):
    # Field name matches the key returned by the /me endpoint and expected by the frontend
    user_id: int
    username: str

    class Config:
        from_attributes = True


class FolderCreate(BaseModel):
    """Payload sent by the frontend when creating a new measurement folder."""
    # User-defined label for the folder, e.g. "Collagen A 2026-06-18".
    name: str


class FolderResponse(BaseModel):
    """Folder row returned to the frontend after creation or listing."""
    # Auto-assigned primary key for the folder.
    id: int
    # Human-readable folder name.
    name: str
    # UTC creation timestamp.
    created_at: datetime
    # Total number of distinct save cycles (curves) stored in this folder.
    curve_count: int = 0
    # Total number of device_data rows across all curves in this folder.
    row_count: int = 0
    # Experiment-wide metadata shared by all curves in this folder.
    velocity: Optional[float] = None
    force_conversion_factor: Optional[float] = None
    z_conversion_factor: Optional[float] = None
    spring_constant: Optional[float] = None
    tip_geometry: Optional[str] = None
    tip_radius: Optional[float] = None
    sampling_rate: Optional[float] = None

    class Config:
        from_attributes = True


class FolderMetadataUpdate(BaseModel):
    """Payload for updating experiment-wide folder metadata before HDF5 export."""
    velocity: Optional[float] = None
    force_conversion_factor: Optional[float] = None
    z_conversion_factor: Optional[float] = None
    spring_constant: Optional[float] = None
    tip_geometry: Optional[str] = None
    tip_radius: Optional[float] = None
    sampling_rate: Optional[float] = None


class FolderExportMetadataResponse(BaseModel):
    """Resolved metadata that will be embedded in the exported HDF5 tip groups."""
    folder_id: int
    folder_name: str
    velocity: float
    force_conversion_factor: float
    z_conversion_factor: float
    spring_constant: float
    tip_geometry: str
    tip_radius: float
    sampling_rate: float


class CurveInfo(BaseModel):
    """Summary of a single save-cycle curve within a folder."""
    # Zero-based index of this curve within the folder.
    curve_index: int
    # Number of device_data rows that belong to this curve.
    row_count: int


# ── Grouped device-data response schemas ─────────────────────────────────────

class DeviceDataRowResponse(BaseModel):
    """A single device_data row returned as part of a grouped hierarchy response."""
    # Primary key of the device_data row.
    id: int
    # ID of the IoT device that produced this reading.
    device_id: str
    # UTC timestamp when the reading was recorded.
    timestamp: datetime
    # Displacement reading in mm.
    displacement: float
    # Force reading in N.
    force: float
    # Folder this row was saved into; None for rows saved before folders existed.
    folder_id: Optional[int] = None
    # Zero-based index of the save-cycle within the folder.
    curve_index: int = 0
    # Indentation phase: 0 = indent (segment0), 1 = retract (segment1).
    phase: int = 0
    # Motor activity flag: 0 = idle, 1 = moving.
    motor_working: int = 0

    class Config:
        from_attributes = True


class GroupedCurveResponse(BaseModel):
    """All device_data rows belonging to one save-cycle (ON→OFF) within a folder."""
    # Zero-based index identifying this curve within its parent folder.
    curve_index: int
    # Pre-computed row count so the frontend can display it without counting rows.
    row_count: int
    # Actual data rows ordered by timestamp ascending.
    rows: List[DeviceDataRowResponse]


class GroupedFolderResponse(BaseModel):
    """A folder (or the null-folder bucket for ungrouped rows) with all its curves."""
    # DB primary key of the folder; None for the synthetic "No folder" group.
    folder_id: Optional[int]
    # Display name shown in the tree header row.
    folder_name: str
    # UTC creation timestamp of the folder; None for the null-folder group.
    folder_created_at: Optional[datetime] = None
    # Curves inside this folder, ordered by curve_index ascending.
    curves: List[GroupedCurveResponse]
