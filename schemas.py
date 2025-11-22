"""
Database Schemas for Barber Booking App

Each Pydantic model maps to a MongoDB collection (lowercased class name).
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal

class Service(BaseModel):
    title: str = Field(..., description="Service name, e.g., Haircut")
    duration_minutes: int = Field(30, ge=10, le=240, description="Service length in minutes")
    price: float = Field(0, ge=0, description="Price in dollars")
    description: Optional[str] = Field(None, description="Optional description")

class Barber(BaseModel):
    name: str = Field(..., description="Barber full name")
    bio: Optional[str] = Field(None, description="Short bio")
    active: bool = Field(True, description="Is the barber taking bookings")

class Booking(BaseModel):
    customer_name: str = Field(..., description="Customer full name")
    phone: str = Field(..., description="Contact phone number")
    service_id: str = Field(..., description="ID of the selected service")
    date: str = Field(..., description="Booking date YYYY-MM-DD")
    time: str = Field(..., description="Start time HH:MM (24h)")
    barber_id: Optional[str] = Field(None, description="Optional barber preference")
    status: Literal["pending","confirmed","cancelled"] = Field("confirmed")
    notes: Optional[str] = Field(None)
