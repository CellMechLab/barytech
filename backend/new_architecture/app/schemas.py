from pydantic import BaseModel, Field
from datetime import datetime

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str


from pydantic import BaseModel, Field
from typing import Optional


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

    class Config:
        from_attributes = True # Enable ORM mode to work with SQLAlchemy models


class UserResponse(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True
