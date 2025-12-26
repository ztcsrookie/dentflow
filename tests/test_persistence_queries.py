import json
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.scheduling.logic import SchedulingLogic
from app.scheduling.models import Appointment, AppointmentStatus, AppointmentType
from app.scheduling.patient_repository import PatientRepository


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def seed_data_dir(data_dir: Path) -> None:
    write_json(
        data_dir / "patients.json",
        {
            "patients": [
                {
                    "id": "P100",
                    "name": "Test Patient",
                    "phone": "+1-555-1000",
                    "email": "test.patient@example.com",
                    "date_of_birth": "1990-01-01",
                    "insurance_info": "Test Insurance",
                    "notes": "Test seed patient",
                }
            ]
        },
    )
    write_json(data_dir / "appointments.json", {"appointments": []})
    write_json(
        data_dir / "availability.json",
        {
            "clinic_hours": {"monday": {"open": "08:00", "close": "17:00"}},
            "appointment_types": {
                "regular_checkup": {
                    "duration": 60,
                    "description": "Routine cleaning and examination",
                }
            },
            "time_slot_rules": {"lunch_break": {"start": "12:00", "end": "13:00"}},
            "dentist_availability": {},
            "holidays_2025": [],
        },
    )


def test_patient_and_appointment_persistence(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    seed_data_dir(data_dir)

    repo = PatientRepository(str(data_dir))
    new_patient = repo.create_patient(
        name="New Patient",
        phone="+1-555-2000",
        email="new.patient@example.com",
        date_of_birth=date(1992, 2, 2),
        insurance_info="Test Insurance",
        notes="Created during test",
    )

    repo_reloaded = PatientRepository(str(data_dir))
    all_patients = repo_reloaded.get_all_patients()
    assert any(p.id == new_patient.id for p in all_patients)

    appointment = Appointment(
        id="A900",
        patient_id=new_patient.id,
        patient_name=new_patient.name,
        datetime=datetime.now() + timedelta(days=3),
        duration=60,
        type=AppointmentType.REGULAR_CHECKUP,
        status=AppointmentStatus.SCHEDULED,
        notes="Test appointment",
        dentist="Dr. Test",
    )
    repo_reloaded.add_or_update_appointment(appointment)

    appointments = repo_reloaded.get_all_appointments()
    assert any(appt.id == "A900" for appt in appointments)

    scheduler = SchedulingLogic(str(data_dir))
    upcoming = scheduler.get_upcoming_appointments()
    assert any(appt.id == "A900" for appt in upcoming)
