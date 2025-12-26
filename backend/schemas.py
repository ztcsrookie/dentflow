from pydantic import BaseModel, Field


class Patient(BaseModel):
    name: str
    dob: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    email: str
    phone: str
    patient_id: str


class Appointment(BaseModel):
    name: str
    dob: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    year: int
    month: int
    day: int
    start_time: str
    end_time: str
