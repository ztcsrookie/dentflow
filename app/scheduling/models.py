from datetime import datetime, date, time
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator


class AppointmentType(str, Enum):
    REGULAR_CHECKUP = "regular_checkup"
    INITIAL_CONSULTATION = "initial_consultation"
    FOLLOW_UP = "follow_up"
    EMERGENCY = "emergency"
    DEEP_CLEANING = "deep_cleaning"
    FILLING = "filling"
    CROWN = "crown"
    EXTRACTION = "extraction"


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    RESCHEDULED = "rescheduled"
    PENDING = "pending"


class Patient(BaseModel):
    id: str
    name: str
    phone: str
    email: str
    date_of_birth: date
    insurance_info: Optional[str] = None
    notes: Optional[str] = None

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat()
        }


class Appointment(BaseModel):
    id: str
    patient_id: str
    patient_name: str
    datetime: datetime
    duration: int = Field(..., gt=0, description="Duration in minutes")
    type: AppointmentType
    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    notes: Optional[str] = None
    dentist: Optional[str] = None

    @validator('datetime')
    def validate_appointment_time(cls, v):
        # Ensure appointment is not in the past for new appointments
        if v < datetime.now():
            raise ValueError('Appointment cannot be in the past')
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ScheduleUpdate(BaseModel):
    patient_name: Optional[str] = None
    status: AppointmentStatus
    original_appointment: Optional[datetime] = None
    new_appointment: Optional[datetime] = None
    notes: Optional[str] = None
    reason: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class TimeSlot(BaseModel):
    start_time: time
    end_time: time
    available: bool = True
    dentist: Optional[str] = None

    class Config:
        json_encoders = {
            time: lambda v: v.isoformat()
        }


class DailySchedule(BaseModel):
    date: date
    time_slots: List[TimeSlot]
    appointments: List[Appointment] = []

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat()
        }


class ClinicHours(BaseModel):
    open: str
    close: str


class AvailabilityRule(BaseModel):
    duration: int
    description: str


class DentistAvailability(BaseModel):
    specialties: List[str]
    schedule: Dict[str, List[str]]


class ClinicAvailability(BaseModel):
    clinic_hours: Dict[str, ClinicHours]
    appointment_types: Dict[AppointmentType, AvailabilityRule]
    time_slot_rules: Dict[str, Any]
    dentist_availability: Dict[str, DentistAvailability]
    holidays: List[date]

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat()
        }


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str
    timestamp: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class PatientRegistrationRequest(BaseModel):
    name: str
    phone: str
    email: str
    date_of_birth: str  # ISO format date string
    insurance_info: Optional[str] = None
    notes: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    patient_email: Optional[str] = None
    conversation_id: Optional[str] = None
    conversation_history: Optional[List[ChatMessage]] = []
    is_new_patient_registration: Optional[bool] = False
    patient_registration_data: Optional[PatientRegistrationRequest] = None


class ChatResponse(BaseModel):
    message: str
    schedule_update: Optional[ScheduleUpdate] = None
    conversation_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BenchmarkScenario(BaseModel):
    id: str
    name: str
    description: str
    patient_message: str
    patient_id: Optional[str] = None
    expected_status: Optional[AppointmentStatus] = None
    expected_response_keywords: List[str] = []
    setup_data: Optional[Dict[str, Any]] = None


class BenchmarkResult(BaseModel):
    scenario_id: str
    passed: bool
    actual_response: str
    actual_schedule_update: Optional[ScheduleUpdate] = None
    expected_vs_actual: Optional[str] = None
    execution_time: float
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SchedulingConstraints(BaseModel):
    preferred_dates: Optional[List[date]] = None
    preferred_times: Optional[List[time]] = None
    appointment_type: Optional[AppointmentType] = None
    dentist_preference: Optional[str] = None
    avoid_times: Optional[List[time]] = None
    max_duration: Optional[int] = None
    notes: Optional[str] = None

    class Config:
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            time: lambda v: v.isoformat() if v else None
        }