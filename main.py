import os
from datetime import datetime, time as dtime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Service, Barber, Booking

app = FastAPI(title="Barber Shop Booking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility functions

def to_collection_name(model_cls) -> str:
    return model_cls.__name__.lower()


def parse_time_str(t: str) -> dtime:
    try:
        hh, mm = t.split(":")
        return dtime(hour=int(hh), minute=int(mm))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM 24h")


def overlaps(start_a: dtime, end_a: dtime, start_b: dtime, end_b: dtime) -> bool:
    return start_a < end_b and start_b < end_a


class PublicBooking(BaseModel):
    id: str = Field(...)
    customer_name: str
    phone: str
    service_title: str
    date: str
    time: str
    duration_minutes: int
    barber_name: Optional[str] = None
    status: str


@app.get("/")
def root():
    return {"message": "Barber Booking API ready"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# Seed default services and barbers if empty
@app.post("/seed")
def seed():
    if db is None:
        raise HTTPException(500, "Database not configured")

    created = {"services": 0, "barbers": 0}

    if db[to_collection_name(Service)].count_documents({}) == 0:
        defaults = [
            {"title": "Hair Cutting", "duration_minutes": 30, "price": 20},
            {"title": "Shaving", "duration_minutes": 20, "price": 10},
            {"title": "Facial", "duration_minutes": 40, "price": 25},
            {"title": "Massage", "duration_minutes": 45, "price": 30},
            {"title": "Hair Spa", "duration_minutes": 60, "price": 40},
            {"title": "Kids Haircut", "duration_minutes": 25, "price": 15},
            {"title": "Hair Color", "duration_minutes": 90, "price": 60},
            {"title": "Beard Trim", "duration_minutes": 15, "price": 8},
            {"title": "Haircut + Beard", "duration_minutes": 45, "price": 30}
        ]
        for s in defaults:
            create_document(to_collection_name(Service), s)
            created["services"] += 1

    if db[to_collection_name(Barber)].count_documents({}) == 0:
        create_document(to_collection_name(Barber), {"name": "Alex", "bio": "Senior Barber"})
        create_document(to_collection_name(Barber), {"name": "Sam", "bio": "Fade Specialist"})
        created["barbers"] += 2

    return {"seeded": created}


@app.get("/services")
def list_services():
    docs = get_documents(to_collection_name(Service))
    res = []
    for d in docs:
        res.append({
            "_id": str(d.get("_id")),
            "title": d.get("title"),
            "duration_minutes": int(d.get("duration_minutes", 30)),
            "price": float(d.get("price", 0)),
            "description": d.get("description")
        })
    return res


class CreateServiceRequest(BaseModel):
    title: str
    duration_minutes: int = Field(ge=10, le=240, default=30)
    price: float = Field(ge=0, default=0)
    description: Optional[str] = None


@app.post("/services")
def create_service(payload: CreateServiceRequest):
    if db is None:
        raise HTTPException(500, "Database not configured")
    # Prevent duplicates by title
    exists = db[to_collection_name(Service)].find_one({"title": payload.title})
    if exists:
        raise HTTPException(400, "Service with this title already exists")
    sid = create_document(to_collection_name(Service), payload.model_dump())
    return {"ok": True, "service_id": sid}


@app.get("/barbers")
def list_barbers():
    docs = get_documents(to_collection_name(Barber))
    res = []
    for d in docs:
        res.append({
            "_id": str(d.get("_id")),
            "name": d.get("name"),
            "bio": d.get("bio"),
            "active": bool(d.get("active", True))
        })
    return res


@app.get("/bookings", response_model=List[PublicBooking])
def list_bookings(date: str = Query(..., description="YYYY-MM-DD")):
    bdocs = get_documents(to_collection_name(Booking), {"date": date})
    # Build maps for services and barbers
    smap = {str(d["_id"]): d for d in get_documents(to_collection_name(Service))}
    bmap = {str(d["_id"]): d for d in get_documents(to_collection_name(Barber))}

    res: List[PublicBooking] = []
    for d in bdocs:
        sid = d.get("service_id")
        sdoc = smap.get(sid) if sid else None
        barber_name = None
        if d.get("barber_id"):
            bdoc = bmap.get(d.get("barber_id"))
            barber_name = bdoc.get("name") if bdoc else None
        duration = (sdoc or {}).get("duration_minutes", 30)
        res.append(PublicBooking(
            id=str(d.get("_id")),
            customer_name=d.get("customer_name"),
            phone=d.get("phone"),
            service_title=(sdoc or {}).get("title", "Service"),
            date=d.get("date"),
            time=d.get("time"),
            duration_minutes=int(duration),
            barber_name=barber_name,
            status=d.get("status", "confirmed")
        ))
    return res


class CreateBookingRequest(BaseModel):
    customer_name: str
    phone: str
    service_id: str
    date: str
    time: str
    barber_id: Optional[str] = None
    notes: Optional[str] = None


@app.post("/book")
def create_booking(payload: CreateBookingRequest):
    # Validate service exists
    try:
        s_id = ObjectId(payload.service_id)
    except Exception:
        raise HTTPException(400, "Invalid service_id")

    sdoc = db[to_collection_name(Service)].find_one({"_id": s_id})
    if not sdoc:
        raise HTTPException(404, "Service not found")

    # If barber specified, ensure exists and active
    bdoc = None
    if payload.barber_id:
        try:
            b_id = ObjectId(payload.barber_id)
        except Exception:
            raise HTTPException(400, "Invalid barber_id")
        bdoc = db[to_collection_name(Barber)].find_one({"_id": b_id})
        if not bdoc:
            raise HTTPException(404, "Barber not found")
        if not bdoc.get("active", True):
            raise HTTPException(400, "Selected barber is not taking bookings")

    # Check overlap on selected date for the same barber (or all if none specified)
    start = parse_time_str(payload.time)
    duration = int(sdoc.get("duration_minutes", 30))
    end_minutes = start.hour * 60 + start.minute + duration
    end = dtime(hour=end_minutes // 60, minute=end_minutes % 60)

    q = {"date": payload.date}
    if payload.barber_id:
        q["barber_id"] = payload.barber_id
    bdocs = get_documents(to_collection_name(Booking), q)
    for b in bdocs:
        b_start = parse_time_str(b.get("time"))
        # Fetch booked service to know its duration
        try:
            booked_service = db[to_collection_name(Service)].find_one({"_id": ObjectId(b.get("service_id"))})
        except Exception:
            booked_service = None
        dur2 = int((booked_service or {}).get("duration_minutes", 30))
        end2_minutes = b_start.hour * 60 + b_start.minute + dur2
        b_end = dtime(hour=end2_minutes // 60, minute=end2_minutes % 60)
        if overlaps(start, end, b_start, b_end):
            raise HTTPException(400, "Selected time overlaps with an existing booking")

    # Create booking
    data = {
        "customer_name": payload.customer_name,
        "phone": payload.phone,
        "service_id": payload.service_id,  # store as string for simplicity
        "date": payload.date,
        "time": payload.time,
        "barber_id": payload.barber_id,
        "status": "confirmed",
        "notes": payload.notes
    }
    booking_id = create_document(to_collection_name(Booking), data)
    return {"ok": True, "booking_id": booking_id}
