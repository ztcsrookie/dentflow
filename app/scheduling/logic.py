import json
import os
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path

from .models import (
    Patient, Appointment, AppointmentStatus, AppointmentType,
    ClinicAvailability, TimeSlot, ScheduleUpdate, SchedulingConstraints,
    ChatMessage, ChatRequest
)


class SchedulingLogic:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.patients: Dict[str, Patient] = {}
        self.appointments: Dict[str, Appointment] = {}
        self.availability: Optional[ClinicAvailability] = None
        self._load_data()

        # Initialize patient repository
        from .patient_repository import PatientRepository
        self.patient_repo = PatientRepository(data_dir)

    def _load_data(self):
        """Load patient, appointment, and availability data from JSON files."""
        try:
            # Load patients
            patients_file = self.data_dir / "patients.json"
            if patients_file.exists():
                with open(patients_file, 'r') as f:
                    patients_data = json.load(f)
                    for patient_data in patients_data.get("patients", []):
                        patient = Patient(**patient_data)
                        self.patients[patient.id] = patient

            # Load appointments
            appointments_file = self.data_dir / "appointments.json"
            if appointments_file.exists():
                with open(appointments_file, 'r') as f:
                    appointments_data = json.load(f)
                    for appt_data in appointments_data.get("appointments", []):
                        # Convert string datetime to datetime object
                        if isinstance(appt_data["datetime"], str):
                            appt_data["datetime"] = datetime.fromisoformat(appt_data["datetime"])
                        appointment = Appointment(**appt_data)
                        self.appointments[appointment.id] = appointment

            # Load availability
            availability_file = self.data_dir / "availability.json"
            if availability_file.exists():
                with open(availability_file, 'r') as f:
                    availability_data = json.load(f)
                    # Convert holiday dates
                    holidays = availability_data.get("holidays_2025", [])
                    availability_data["holidays"] = [datetime.fromisoformat(h).date() for h in holidays]
                    self.availability = ClinicAvailability(**availability_data)

        except Exception as e:
            print(f"Error loading data: {e}")

    def save_data(self):
        """Save current state to JSON files."""
        try:
            # Save patients
            patients_file = self.data_dir / "patients.json"
            patients_data = {"patients": [patient.dict() for patient in self.patients.values()]}
            with open(patients_file, 'w') as f:
                json.dump(patients_data, f, indent=2, default=str)

            # Save appointments
            appointments_file = self.data_dir / "appointments.json"
            appointments_data = {"appointments": [appt.dict() for appt in self.appointments.values()]}
            with open(appointments_file, 'w') as f:
                json.dump(appointments_data, f, indent=2, default=str)

        except Exception as e:
            print(f"Error saving data: {e}")

    def find_patient_by_name(self, name: str) -> Optional[Patient]:
        """Find a patient by name (case-insensitive) using repository."""
        lookup_result = self.patient_repo.find_patient_by_identifiers(name=name)
        return lookup_result.patient if lookup_result.is_confident_match() else None

    def find_patient_by_id(self, patient_id: str) -> Optional[Patient]:
        """Find a patient by ID using repository."""
        lookup_result = self.patient_repo.find_patient_by_identifiers(patient_id=patient_id)
        return lookup_result.patient if lookup_result.is_confident_match() else None

    def get_appointments_for_patient(self, patient_id: str) -> List[Appointment]:
        """Get all appointments for a specific patient."""
        return [appt for appt in self.appointments.values() if appt.patient_id == patient_id]

    def get_upcoming_appointments(self, patient_id: Optional[str] = None) -> List[Appointment]:
        """Get upcoming appointments, optionally filtered by patient."""
        if patient_id:
            # Use repository for patient-specific appointments
            patient = self.find_patient_by_id(patient_id)
            if patient:
                return self.patient_repo.get_upcoming_appointments(patient)
            return []

        # For all patients, use the original logic
        now = datetime.now()
        appointments = [appt for appt in self.appointments.values()
                       if appt.datetime > now and appt.status in [AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED]]

        return sorted(appointments, key=lambda x: x.datetime)

    def find_available_slots(self,
                           preferred_date: date,
                           appointment_type: AppointmentType,
                           dentist: Optional[str] = None) -> List[TimeSlot]:
        """Find available time slots for a specific date and appointment type."""
        if not self.availability:
            return []

        # Check if date is a holiday or weekend
        weekday = preferred_date.strftime("%A").lower()
        if preferred_date in self.availability.holidays:
            return []

        # Get clinic hours for the day
        clinic_hours = self.availability.clinic_hours.get(weekday)
        if not clinic_hours or clinic_hours.open == "closed":
            return []

        # Get appointment duration
        appointment_info = self.availability.appointment_types.get(appointment_type)
        if not appointment_info:
            return []

        duration = appointment_info.duration

        # Parse clinic hours
        open_time = datetime.strptime(clinic_hours.open, "%H:%M").time()
        close_time = datetime.strptime(clinic_hours.close, "%H:%M").time()

        # Get existing appointments for the day
        day_start = datetime.combine(preferred_date, time.min)
        day_end = datetime.combine(preferred_date, time.max)
        existing_appts = [appt for appt in self.appointments.values()
                         if day_start <= appt.datetime <= day_end
                         and appt.status not in [AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED]]

        available_slots = []
        current_time = datetime.combine(preferred_date, open_time)

        while current_time.time() <= close_time:
            slot_end = current_time + timedelta(minutes=duration)

            # Check if slot is within clinic hours and doesn't conflict with lunch
            if (slot_end.time() <= close_time and
                not self._is_lunch_break(current_time.time(), slot_end.time())):

                # Check for conflicts with existing appointments
                conflict = False
                for appt in existing_appts:
                    appt_end = appt.datetime + timedelta(minutes=appt.duration)
                    if (current_time < appt_end and slot_end > appt.datetime):
                        conflict = True
                        break

                if not conflict:
                    time_slot = TimeSlot(
                        start_time=current_time.time(),
                        end_time=slot_end.time(),
                        available=True,
                        dentist=dentist
                    )
                    available_slots.append(time_slot)

            current_time += timedelta(minutes=15)  # Move to next 15-minute slot

        return available_slots

    def _is_lunch_break(self, start_time: time, end_time: time) -> bool:
        """Check if a time slot conflicts with lunch break."""
        if not self.availability:
            return False

        lunch_start = datetime.strptime(self.availability.time_slot_rules.get("lunch_break", {}).get("start", "12:00"), "%H:%M").time()
        lunch_end = datetime.strptime(self.availability.time_slot_rules.get("lunch_break", {}).get("end", "13:00"), "%H:%M").time()

        return start_time < lunch_end and end_time > lunch_start

    def schedule_appointment(self,
                           patient_id: str,
                           preferred_datetime: datetime,
                           appointment_type: AppointmentType,
                           dentist: Optional[str] = None,
                           notes: Optional[str] = None) -> Optional[Appointment]:
        """Schedule a new appointment."""
        patient = self.find_patient_by_id(patient_id)
        if not patient:
            return None

        # Check if slot is available
        available_slots = self.find_available_slots(
            preferred_datetime.date(), appointment_type, dentist
        )

        target_slot = None
        for slot in available_slots:
            slot_start = datetime.combine(preferred_datetime.date(), slot.start_time)
            if abs((slot_start - preferred_datetime).total_seconds()) < 60:  # Within 1 minute
                target_slot = slot
                break

        if not target_slot:
            return None

        # Get duration
        duration = 60  # Default
        if self.availability and appointment_type in self.availability.appointment_types:
            duration = self.availability.appointment_types[appointment_type].duration

        # Create appointment
        appointment_id = f"A{len(self.appointments) + 1:03d}"
        appointment = Appointment(
            id=appointment_id,
            patient_id=patient_id,
            patient_name=patient.name,
            datetime=preferred_datetime,
            duration=duration,
            type=appointment_type,
            status=AppointmentStatus.SCHEDULED,
            notes=notes,
            dentist=dentist
        )

        self.appointments[appointment_id] = appointment
        self.save_data()

        return appointment

    def cancel_appointment(self, appointment_id: str) -> bool:
        """Cancel an appointment."""
        appointment = self.appointments.get(appointment_id)
        if not appointment:
            return False

        appointment.status = AppointmentStatus.CANCELLED
        self.save_data()
        return True

    def reschedule_appointment(self,
                             appointment_id: str,
                             new_datetime: datetime) -> Optional[Appointment]:
        """Reschedule an existing appointment."""
        appointment = self.appointments.get(appointment_id)
        if not appointment:
            return None

        # Check if new slot is available
        available_slots = self.find_available_slots(
            new_datetime.date(), appointment.type, appointment.dentist
        )

        target_slot = None
        for slot in available_slots:
            slot_start = datetime.combine(new_datetime.date(), slot.start_time)
            if abs((slot_start - new_datetime).total_seconds()) < 60:  # Within 1 minute
                target_slot = slot
                break

        if not target_slot:
            return None

        # Update appointment
        old_datetime = appointment.datetime
        appointment.datetime = new_datetime
        appointment.status = AppointmentStatus.RESCHEDULED

        self.save_data()
        return appointment

    def confirm_appointment(self, appointment_id: str) -> bool:
        """Confirm an appointment."""
        appointment = self.appointments.get(appointment_id)
        if not appointment:
            return False

        appointment.status = AppointmentStatus.CONFIRMED
        self.save_data()
        return True

    def get_appointment_suggestions(self,
                                  patient_id: str,
                                  preferred_dates: Optional[List[date]] = None,
                                  appointment_type: AppointmentType = AppointmentType.REGULAR_CHECKUP,
                                  dentist: Optional[str] = None) -> List[Tuple[date, List[TimeSlot]]]:
        """Get appointment suggestions for a patient."""
        if not preferred_dates:
            # Default to next 7 days
            today = date.today()
            preferred_dates = [today + timedelta(days=i) for i in range(1, 8)]

        suggestions = []
        for pref_date in preferred_dates:
            slots = self.find_available_slots(pref_date, appointment_type, dentist)
            if slots:
                suggestions.append((pref_date, slots))

        return suggestions

    def create_schedule_update(self,
                             patient_name: str,
                             status: AppointmentStatus,
                             original_appointment: Optional[datetime] = None,
                             new_appointment: Optional[datetime] = None,
                             notes: Optional[str] = None,
                             reason: Optional[str] = None) -> ScheduleUpdate:
        """Create a schedule update object."""
        return ScheduleUpdate(
            patient_name=patient_name,
            status=status,
            original_appointment=original_appointment,
            new_appointment=new_appointment,
            notes=notes,
            reason=reason
        )

    def process_patient_request(self, chat_request: ChatRequest) -> Tuple[str, Optional[ScheduleUpdate]]:
        """
        Process a patient's scheduling request and return a response with schedule update.
        This is a simplified version - the actual LLM processing would happen elsewhere.
        """
        patient = None
        if chat_request.patient_id:
            patient = self.find_patient_by_id(chat_request.patient_id)
        elif chat_request.patient_name:
            patient = self.find_patient_by_name(chat_request.patient_name)

        if not patient:
            response = "I couldn't find your patient record. Could you please provide your full name or patient ID?"
            return response, None

        message = chat_request.message.lower()
        upcoming_appts = self.get_upcoming_appointments(patient.id)

        # Handle different request types
        if "confirm" in message or "confirmation" in message:
            if upcoming_appts:
                appointment = upcoming_appts[0]
                self.confirm_appointment(appointment.id)
                schedule_update = self.create_schedule_update(
                    patient_name=patient.name,
                    status=AppointmentStatus.CONFIRMED,
                    original_appointment=appointment.datetime,
                    notes="Appointment confirmed by patient"
                )
                response = f"Perfect! I've confirmed your appointment on {appointment.datetime.strftime('%B %d at %I:%M %p')}. We look forward to seeing you!"
                return response, schedule_update
            else:
                response = "I don't see any upcoming appointments for you. Would you like to schedule one?"
                return response, None

        elif "cancel" in message:
            if upcoming_appts:
                appointment = upcoming_appts[0]
                self.cancel_appointment(appointment.id)
                schedule_update = self.create_schedule_update(
                    patient_name=patient.name,
                    status=AppointmentStatus.CANCELLED,
                    original_appointment=appointment.datetime,
                    notes="Appointment cancelled by patient"
                )
                response = f"I've cancelled your appointment on {appointment.datetime.strftime('%B %d at %I:%M %p')}. Would you like to reschedule for a different time?"
                return response, schedule_update
            else:
                response = "I don't see any upcoming appointments that can be cancelled."
                return response, None

        elif "reschedule" in message or "change" in message or "different time" in message:
            if upcoming_appts:
                appointment = upcoming_appts[0]
                suggestions = self.get_appointment_suggestions(
                    patient.id,
                    appointment_type=appointment.type,
                    dentist=appointment.dentist
                )

                if suggestions:
                    next_date, slots = suggestions[0]
                    first_slot = slots[0]
                    response = f"I understand you need to reschedule. I have an opening on {next_date.strftime('%B %d')} at {first_slot.start_time.strftime('%I:%M %p')}. Would that work for you?"
                    return response, None
                else:
                    response = "I'd be happy to help you reschedule. Let me check what's available and get back to you with some options."
                    return response, None
            else:
                response = "I don't see any upcoming appointments to reschedule."
                return response, None

        else:
            # Default: list upcoming appointments
            if upcoming_appts:
                appointment = upcoming_appts[0]
                response = f"Your next appointment is scheduled for {appointment.datetime.strftime('%B %d at %I:%M %p')} for a {appointment.type.replace('_', ' ')}. Would you like to confirm or make any changes?"
                return response, None
            else:
                response = "I don't see any upcoming appointments for you. Would you like to schedule a new appointment?"
                return response, None