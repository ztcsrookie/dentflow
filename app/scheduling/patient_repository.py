import json
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

from .models import Patient, Appointment


class PatientLookupResult:
    """Result of a patient lookup operation."""
    def __init__(self, patient: Optional[Patient] = None, is_new_patient: bool = False,
                 missing_fields: List[str] = None, multiple_matches: List[Patient] = None):
        self.patient = patient
        self.is_new_patient = is_new_patient
        self.missing_fields = missing_fields or []
        self.multiple_matches = multiple_matches or []

    def is_confident_match(self) -> bool:
        """Return True if we have a confident single patient match."""
        return self.patient is not None and not self.multiple_matches

    def needs_more_info(self) -> bool:
        """Return True if we need more information from the user."""
        return self.is_new_patient or bool(self.multiple_matches)


class PatientRepository:
    """Repository for handling patient data operations."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.patients_file = self.data_dir / "patients.json"
        self.appointments_file = self.data_dir / "appointments.json"
        self._patients_cache: Dict[str, Patient] = {}
        self._load_patients()

    def _load_patients(self):
        """Load patients from JSON file into cache."""
        try:
            if self.patients_file.exists():
                with open(self.patients_file, 'r') as f:
                    data = json.load(f)
                    self._patients_cache = {}
                    for patient_data in data.get("patients", []):
                        patient = Patient(**patient_data)
                        self._patients_cache[patient.id] = patient
        except Exception as e:
            print(f"Error loading patients: {e}")
            self._patients_cache = {}

    def _save_patients(self):
        """Save patients from cache to JSON file."""
        try:
            # Ensure directory exists
            self.data_dir.mkdir(exist_ok=True)

            patients_data = {
                "patients": [patient.dict() for patient in self._patients_cache.values()]
            }

            # Write to temporary file first, then rename to avoid corruption
            temp_file = self.patients_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(patients_data, f, indent=2, default=str)

            temp_file.rename(self.patients_file)
            print(f"Saved {len(self._patients_cache)} patients to {self.patients_file}")

        except Exception as e:
            print(f"Error saving patients: {e}")
            raise

    def _load_appointments(self) -> List[Appointment]:
        """Load appointments from JSON file."""
        try:
            if self.appointments_file.exists():
                with open(self.appointments_file, 'r') as f:
                    data = json.load(f)
                    appointments = []
                    for appt_data in data.get("appointments", []):
                        # Convert string datetime to datetime object
                        if isinstance(appt_data["datetime"], str):
                            appt_data["datetime"] = datetime.fromisoformat(appt_data["datetime"])
                        appointments.append(Appointment(**appt_data))
                    return appointments
        except Exception as e:
            print(f"Error loading appointments: {e}")
        return []

    def _save_appointments(self, appointments: List[Appointment]) -> None:
        """Save appointments to JSON file."""
        try:
            self.data_dir.mkdir(exist_ok=True)
            data = {"appointments": [appt.dict() for appt in appointments]}
            temp_file = self.appointments_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            temp_file.rename(self.appointments_file)
        except Exception as e:
            print(f"Error saving appointments: {e}")
            raise

    def get_all_appointments(self) -> List[Appointment]:
        """Get all appointments."""
        return self._load_appointments()

    def add_or_update_appointment(self, appointment: Appointment) -> Appointment:
        """Add a new appointment or update an existing one by ID."""
        appointments = self._load_appointments()
        updated = False
        for idx, appt in enumerate(appointments):
            if appt.id == appointment.id:
                appointments[idx] = appointment
                updated = True
                break
        if not updated:
            appointments.append(appointment)
        self._save_appointments(appointments)
        return appointment

    def find_patient_by_identifiers(self, name: Optional[str] = None,
                                  phone: Optional[str] = None,
                                  email: Optional[str] = None,
                                  patient_id: Optional[str] = None) -> PatientLookupResult:
        """
        Find a patient using various identifiers.
        Returns a PatientLookupResult indicating if we found the patient or need more info.
        """
        # If patient_id is provided, try exact match first
        if patient_id:
            patient = self._patients_cache.get(patient_id)
            if patient:
                return PatientLookupResult(patient=patient)

        # Normalize search terms
        name_normalized = name.lower().strip() if name else None
        phone_normalized = self._normalize_phone(phone) if phone else None
        email_normalized = email.lower().strip() if email else None

        matches = []

        # Search through all patients
        for patient in self._patients_cache.values():
            score = 0

            # Name matching (highest weight)
            if name_normalized:
                if patient.name.lower().strip() == name_normalized:
                    score += 3
                elif name_normalized in patient.name.lower():
                    score += 1

            # Phone matching (high weight)
            if phone_normalized:
                if self._normalize_phone(patient.phone) == phone_normalized:
                    score += 3

            # Email matching (medium weight)
            if email_normalized:
                if patient.email.lower().strip() == email_normalized:
                    score += 2

            if score > 0:
                matches.append((patient, score))

        # Sort by score (highest first)
        matches.sort(key=lambda x: x[1], reverse=True)

        # Analyze results
        if not matches:
            # No matches found - this is a new patient
            missing_fields = self._get_required_fields_for_new_patient(name, phone, email)
            return PatientLookupResult(is_new_patient=True, missing_fields=missing_fields)

        # Single high-confidence match
        if len(matches) == 1 or (len(matches) > 1 and matches[0][1] > matches[1][1]):
            return PatientLookupResult(patient=matches[0][0])

        # Multiple matches with similar scores
        if len(matches) > 1 and abs(matches[0][1] - matches[1][1]) <= 1:
            multiple_patients = [match[0] for match in matches[:3]]  # Limit to top 3
            return PatientLookupResult(multiple_matches=multiple_patients)

        # Default to best match
        return PatientLookupResult(patient=matches[0][0])

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number by removing non-digit characters."""
        return re.sub(r'\D', '', phone) if phone else ""

    def _get_required_fields_for_new_patient(self, name: Optional[str],
                                           phone: Optional[str],
                                           email: Optional[str]) -> List[str]:
        """Determine what fields are still needed for a new patient."""
        missing_fields = []

        if not name:
            missing_fields.append("name")
        if not phone:
            missing_fields.append("phone")
        if not email:
            missing_fields.append("email")

        # Always add other required fields for new patients
        missing_fields.extend(["date_of_birth", "insurance_info"])

        return missing_fields

    def _generate_patient_id(self) -> str:
        """Generate a unique patient ID following the existing pattern."""
        max_id = 0
        for patient_id in self._patients_cache.keys():
            if patient_id.startswith('P'):
                try:
                    num = int(patient_id[1:])
                    max_id = max(max_id, num)
                except ValueError:
                    continue

        new_id = max_id + 1
        return f"P{new_id:03d}"

    def create_patient(self, name: str, phone: str, email: str,
                      date_of_birth: datetime,
                      insurance_info: Optional[str] = None,
                      notes: Optional[str] = None) -> Patient:
        """
        Create a new patient and save to file.
        """
        patient_id = self._generate_patient_id()

        patient = Patient(
            id=patient_id,
            name=name.strip(),
            phone=phone.strip(),
            email=email.strip(),
            date_of_birth=date_of_birth,
            insurance_info=insurance_info.strip() if insurance_info else None,
            notes=notes.strip() if notes else None
        )

        # Add to cache and save
        self._patients_cache[patient_id] = patient
        self._save_patients()

        print(f"Created new patient: {patient.name} (ID: {patient_id})")
        return patient

    def get_patient_appointments(self, patient: Patient) -> List[Appointment]:
        """Get all appointments for a specific patient."""
        appointments = self._load_appointments()
        patient_appts = [
            appt for appt in appointments
            if appt.patient_id == patient.id or appt.patient_name == patient.name
        ]

        # Sort by datetime (most recent first)
        patient_appts.sort(key=lambda x: x.datetime, reverse=True)
        return patient_appts

    def get_upcoming_appointments(self, patient: Patient) -> List[Appointment]:
        """Get upcoming appointments for a patient."""
        all_appts = self.get_patient_appointments(patient)
        now = datetime.now()

        upcoming = [
            appt for appt in all_appts
            if appt.datetime > now and appt.status not in ["cancelled", "completed"]
        ]

        return sorted(upcoming, key=lambda x: x.datetime)

    def get_all_patients(self) -> List[Patient]:
        """Get all patients."""
        return list(self._patients_cache.values())

    def validate_patient_data(self, patient_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate patient data before creating a new patient."""
        errors = []

        # Required fields
        required_fields = ["name", "phone", "email", "date_of_birth"]
        for field in required_fields:
            if field not in patient_data or not patient_data[field]:
                errors.append(f"Missing required field: {field}")

        # Email format
        if "email" in patient_data:
            email = patient_data["email"]
            if '@' not in email:
                errors.append("Invalid email format")

        # Phone format (basic validation)
        if "phone" in patient_data:
            phone = patient_data["phone"]
            digits = re.sub(r'\D', '', phone)
            if len(digits) < 10:
                errors.append("Phone number must have at least 10 digits")

        # Name length
        if "name" in patient_data:
            name = patient_data["name"]
            if len(name.strip()) < 2:
                errors.append("Name must be at least 2 characters long")

        return len(errors) == 0, errors
