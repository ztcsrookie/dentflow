import json
import os
import secrets
import string
from pathlib import Path
from typing import List, Dict, Any

from filelock import FileLock

from backend.schemas import Patient, Appointment

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PATIENTS_PATH = DATA_DIR / "patients.json"
APPOINTMENTS_PATH = DATA_DIR / "appointments.json"


def _ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in (PATIENTS_PATH, APPOINTMENTS_PATH):
        if not path.exists():
            path.write_text("[]", encoding="utf-8")


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    _ensure_data_files()
    lock = FileLock(str(path) + ".lock")
    with lock:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return data


def _atomic_write(path: Path, data: List[Dict[str, Any]]) -> None:
    lock = FileLock(str(path) + ".lock")
    with lock:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)


def _generate_patient_id(existing_ids: set[str], length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        patient_id = "".join(secrets.choice(alphabet) for _ in range(length))
        if patient_id not in existing_ids:
            return patient_id


def is_new_patient(name: str, dob: str) -> bool:
    patients = _read_json_list(PATIENTS_PATH)
    for patient in patients:
        if patient.get("name") == name and patient.get("dob") == dob:
            return False
    return True


def registration_new_patient(name: str, dob: str, email: str, phone: str) -> dict:
    patients = _read_json_list(PATIENTS_PATH)
    existing_ids = {p.get("patient_id") for p in patients if p.get("patient_id")}
    patient_id = _generate_patient_id(existing_ids)

    patient = Patient(
        name=name,
        dob=dob,
        email=email,
        phone=phone,
        patient_id=patient_id,
    )
    patients.append(patient.model_dump())
    _atomic_write(PATIENTS_PATH, patients)
    return patient.model_dump()


def _time_to_minutes(time_str: str) -> int:
    hour, minute = time_str.split(":")
    return int(hour) * 60 + int(minute)


def is_conflict_appointment(year: int, month: int, day: int, start_time: str, end_time: str) -> bool:
    appointments = _read_json_list(APPOINTMENTS_PATH)
    new_start = _time_to_minutes(start_time)
    new_end = _time_to_minutes(end_time)

    for appt in appointments:
        if appt.get("year") == year and appt.get("month") == month and appt.get("day") == day:
            existing_start = _time_to_minutes(appt.get("start_time"))
            existing_end = _time_to_minutes(appt.get("end_time"))
            overlap = new_start < existing_end and new_end > existing_start
            if overlap:
                return True
    return False


def make_appointment(
    name: str,
    dob: str,
    year: int,
    month: int,
    day: int,
    start_time: str,
    end_time: str,
) -> dict:
    appointments = _read_json_list(APPOINTMENTS_PATH)
    appointment = Appointment(
        name=name,
        dob=dob,
        year=year,
        month=month,
        day=day,
        start_time=start_time,
        end_time=end_time,
    )
    appointments.append(appointment.model_dump())
    _atomic_write(APPOINTMENTS_PATH, appointments)
    return appointment.model_dump()


def get_patient_info_and_appointments(name: str, dob: str) -> dict:
    patients = _read_json_list(PATIENTS_PATH)
    appointments = _read_json_list(APPOINTMENTS_PATH)

    patient_info = None
    for patient in patients:
        if patient.get("name") == name and patient.get("dob") == dob:
            patient_info = patient
            break

    patient_appts = [
        appt for appt in appointments if appt.get("name") == name and appt.get("dob") == dob
    ]

    return {
        "patient": patient_info,
        "appointments": patient_appts,
    }
