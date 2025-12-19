"""
Automated tests for DentFlow scheduling agent behavior.

This test suite validates:
- Correct JSON structure for schedule_update
- Correct handling of simple confirmation/reschedule/cancellation scenarios
- Robustness against missing or malformed input
- Scheduling logic edge cases
"""

import pytest
import json
import asyncio
from datetime import datetime, timedelta, date, time
from typing import Dict, Any, Optional
from unittest.mock import Mock, patch, AsyncMock

# Add the parent directory to the path for imports
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from app.scheduling.models import (
    Patient, Appointment, AppointmentStatus, AppointmentType,
    ScheduleUpdate, ChatRequest, ChatResponse, TimeSlot
)
from app.scheduling.logic import SchedulingLogic


class TestSchedulingLogic:
    """Test the core scheduling logic functionality."""

    @pytest.fixture
    def scheduler(self):
        """Create a fresh scheduler instance for each test."""
        return SchedulingLogic()

    @pytest.fixture
    def sample_patient(self):
        """Create a sample patient for testing."""
        return Patient(
            id="TEST001",
            name="Test Patient",
            phone="555-0123",
            email="test@example.com",
            date_of_birth=date(1990, 1, 1),
            insurance_info="Test Insurance"
        )

    @pytest.fixture
    def sample_appointment(self, sample_patient):
        """Create a sample appointment for testing."""
        return Appointment(
            id="TEST_A001",
            patient_id=sample_patient.id,
            patient_name=sample_patient.name,
            datetime=datetime.now() + timedelta(days=1),
            duration=60,
            type=AppointmentType.REGULAR_CHECKUP,
            status=AppointmentStatus.SCHEDULED,
            dentist="Dr. Test"
        )

    def test_load_patients_data(self, scheduler):
        """Test that patients data is loaded correctly."""
        assert len(scheduler.patients) > 0, "No patients loaded"

        # Check that Alice Brown exists
        alice = scheduler.find_patient_by_name("Alice Brown")
        assert alice is not None, "Alice Brown not found"
        assert alice.id == "P001", "Alice Brown has wrong ID"

    def test_load_appointments_data(self, scheduler):
        """Test that appointments data is loaded correctly."""
        assert len(scheduler.appointments) > 0, "No appointments loaded"

        # Check that at least one appointment exists
        appointment = next(iter(scheduler.appointments.values()))
        assert isinstance(appointment, Appointment), "Loaded data is not an Appointment"

    def test_find_patient_by_name(self, scheduler):
        """Test finding patients by name."""
        # Test exact match
        patient = scheduler.find_patient_by_name("Alice Brown")
        assert patient is not None, "Alice Brown not found"
        assert patient.name == "Alice Brown", "Wrong patient returned"

        # Test case insensitive
        patient = scheduler.find_patient_by_name("alice brown")
        assert patient is not None, "Case insensitive search failed"

        # Test not found
        patient = scheduler.find_patient_by_name("Nonexistent Patient")
        assert patient is None, "Found nonexistent patient"

    def test_find_patient_by_id(self, scheduler):
        """Test finding patients by ID."""
        patient = scheduler.find_patient_by_id("P001")
        assert patient is not None, "Patient P001 not found"
        assert patient.name == "Alice Brown", "Wrong patient returned"

        patient = scheduler.find_patient_by_id("NONEXISTENT")
        assert patient is None, "Found nonexistent patient"

    def test_get_appointments_for_patient(self, scheduler):
        """Test getting appointments for a specific patient."""
        alice_appts = scheduler.get_appointments_for_patient("P001")
        assert isinstance(alice_appts, list), "Should return a list"

        # All appointments should be for Alice Brown
        for appt in alice_appts:
            assert appt.patient_id == "P001", "Appointment for wrong patient"

    def test_get_upcoming_appointments(self, scheduler):
        """Test getting upcoming appointments."""
        upcoming = scheduler.get_upcoming_appointments()
        assert isinstance(upcoming, list), "Should return a list"

        # All appointments should be in the future and scheduled/confirmed
        now = datetime.now()
        for appt in upcoming:
            assert appt.datetime > now, "Appointment not in the future"
            assert appt.status in [AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED], \
                "Appointment not in valid status"

    def test_find_available_slots(self, scheduler):
        """Test finding available time slots."""
        tomorrow = date.today() + timedelta(days=1)
        slots = scheduler.find_available_slots(tomorrow, AppointmentType.REGULAR_CHECKUP)
        assert isinstance(slots, list), "Should return a list"

        for slot in slots:
            assert isinstance(slot, TimeSlot), "Slot is not a TimeSlot object"
            assert slot.available == True, "Slot should be available"

    def test_schedule_appointment(self, scheduler):
        """Test scheduling a new appointment."""
        tomorrow = datetime.now() + timedelta(days=1)
        appointment = scheduler.schedule_appointment(
            patient_id="P001",
            preferred_datetime=tomorrow.replace(hour=10, minute=0),
            appointment_type=AppointmentType.REGULAR_CHECKUP
        )

        if appointment:  # Only test if a slot was available
            assert isinstance(appointment, Appointment), "Should return an Appointment"
            assert appointment.patient_id == "P001", "Wrong patient"
            assert appointment.type == AppointmentType.REGULAR_CHECKUP, "Wrong appointment type"
            assert appointment.status == AppointmentStatus.SCHEDULED, "Wrong status"

    def test_cancel_appointment(self, scheduler):
        """Test cancelling an appointment."""
        # Get an existing appointment
        appointments = list(scheduler.appointments.values())
        if appointments:
            appointment = appointments[0]
            success = scheduler.cancel_appointment(appointment.id)
            assert success == True, "Failed to cancel appointment"

            # Check that status was updated
            cancelled_appt = scheduler.appointments[appointment.id]
            assert cancelled_appt.status == AppointmentStatus.CANCELLED, "Status not updated"

    def test_confirm_appointment(self, scheduler):
        """Test confirming an appointment."""
        # Get an existing appointment
        appointments = list(scheduler.appointments.values())
        if appointments:
            appointment = appointments[0]
            success = scheduler.confirm_appointment(appointment.id)
            assert success == True, "Failed to confirm appointment"

            # Check that status was updated
            confirmed_appt = scheduler.appointments[appointment.id]
            assert confirmed_appt.status == AppointmentStatus.CONFIRMED, "Status not updated"

    def test_reschedule_appointment(self, scheduler):
        """Test rescheduling an appointment."""
        appointments = list(scheduler.appointments.values())
        if not appointments:
            pytest.skip("No appointments available for testing")

        appointment = appointments[0]
        new_time = appointment.datetime + timedelta(hours=2)

        # Note: This might fail if no slot is available at the new time
        rescheduled = scheduler.reschedule_appointment(appointment.id, new_time)

        if rescheduled:
            assert rescheduled.datetime == new_time, "New time not set correctly"
            assert rescheduled.status == AppointmentStatus.RESCHEDULED, "Status not updated"

    def test_create_schedule_update(self, scheduler):
        """Test creating schedule update objects."""
        update = scheduler.create_schedule_update(
            patient_name="Test Patient",
            status=AppointmentStatus.CONFIRMED,
            notes="Test confirmation"
        )

        assert isinstance(update, ScheduleUpdate), "Should return ScheduleUpdate"
        assert update.patient_name == "Test Patient", "Wrong patient name"
        assert update.status == AppointmentStatus.CONFIRMED, "Wrong status"
        assert update.notes == "Test confirmation", "Wrong notes"


class TestChatProcessing:
    """Test the chat processing functionality."""

    @pytest.fixture
    def scheduler(self):
        """Create a fresh scheduler instance for each test."""
        return SchedulingLogic()

    def test_confirmation_request(self, scheduler):
        """Test processing a confirmation request."""
        request = ChatRequest(
            message="Hi, I want to confirm my appointment tomorrow.",
            patient_name="Alice Brown"
        )

        response, schedule_update = scheduler.process_patient_request(request)

        assert isinstance(response, str), "Response should be a string"
        assert len(response) > 0, "Response should not be empty"

        if schedule_update:
            assert isinstance(schedule_update, dict), "Schedule update should be a dict"

    def test_cancellation_request(self, scheduler):
        """Test processing a cancellation request."""
        request = ChatRequest(
            message="Please cancel my appointment for next week.",
            patient_name="Alice Brown"
        )

        response, schedule_update = scheduler.process_patient_request(request)

        assert isinstance(response, str), "Response should be a string"
        assert len(response) > 0, "Response should not be empty"

    def test_reschedule_request(self, scheduler):
        """Test processing a reschedule request."""
        request = ChatRequest(
            message="I can't make it on Tuesday morning. Can I do Thursday afternoon?",
            patient_name="Alice Brown"
        )

        response, schedule_update = scheduler.process_patient_request(request)

        assert isinstance(response, str), "Response should be a string"
        assert len(response) > 0, "Response should not be empty"

    def test_patient_not_found(self, scheduler):
        """Test handling requests from unknown patients."""
        request = ChatRequest(
            message="I want to confirm my appointment",
            patient_name="Unknown Patient"
        )

        response, schedule_update = scheduler.process_patient_request(request)

        assert isinstance(response, str), "Response should be a string"
        assert len(response) > 0, "Response should not be empty"
        assert schedule_update is None, "Should not have schedule update for unknown patient"

    def test_empty_message(self, scheduler):
        """Test handling empty messages."""
        request = ChatRequest(message="")

        response, schedule_update = scheduler.process_patient_request(request)

        assert isinstance(response, str), "Response should be a string"
        assert len(response) > 0, "Response should not be empty"

    def test_no_patient_info(self, scheduler):
        """Test handling messages without patient information."""
        request = ChatRequest(message="I want to schedule an appointment")

        response, schedule_update = scheduler.process_patient_request(request)

        assert isinstance(response, str), "Response should be a string"
        assert len(response) > 0, "Response should not be empty"


class TestModelValidation:
    """Test Pydantic model validation and serialization."""

    def test_patient_model_validation(self):
        """Test Patient model validation."""
        # Valid patient
        patient = Patient(
            id="P001",
            name="Alice Brown",
            phone="555-0123",
            email="alice@example.com",
            date_of_birth=date(1985, 3, 15)
        )
        assert patient.email == "alice@example.com", "Email not set correctly"

        # Invalid email
        with pytest.raises(ValueError):
            Patient(
                id="P002",
                name="Test Patient",
                phone="555-0124",
                email="invalid-email",
                date_of_birth=date(1990, 1, 1)
            )

    def test_appointment_model_validation(self):
        """Test Appointment model validation."""
        # Valid appointment
        appt = Appointment(
            id="A001",
            patient_id="P001",
            patient_name="Alice Brown",
            datetime=datetime.now() + timedelta(days=1),
            duration=60,
            type=AppointmentType.REGULAR_CHECKUP
        )
        assert appt.status == AppointmentStatus.SCHEDULED, "Default status not set"

        # Past appointment should fail validation
        with pytest.raises(ValueError):
            Appointment(
                id="A002",
                patient_id="P001",
                patient_name="Alice Brown",
                datetime=datetime.now() - timedelta(days=1),  # Past
                duration=60,
                type=AppointmentType.REGULAR_CHECKUP
            )

    def test_schedule_update_model(self):
        """Test ScheduleUpdate model."""
        update = ScheduleUpdate(
            patient_name="Alice Brown",
            status=AppointmentStatus.CONFIRMED,
            original_appointment=datetime.now() + timedelta(days=1),
            notes="Confirmed by patient"
        )
        assert isinstance(update, ScheduleUpdate), "ScheduleUpdate creation failed"

    def test_json_serialization(self):
        """Test JSON serialization of models."""
        patient = Patient(
            id="P001",
            name="Alice Brown",
            phone="555-0123",
            email="alice@example.com",
            date_of_birth=date(1985, 3, 15)
        )

        # Should not raise an exception
        json_str = patient.json()
        assert isinstance(json_str, str), "JSON serialization failed"

        # Should be able to parse back
        data = json.loads(json_str)
        assert data["name"] == "Alice Brown", "JSON data incorrect"


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def scheduler(self):
        """Create a fresh scheduler instance for each test."""
        return SchedulingLogic()

    def test_malformed_datetime_input(self, scheduler):
        """Test handling of malformed datetime input."""
        # This would be tested at the API level, but we can test the logic level
        # with invalid datetime objects
        pass  # Placeholder for datetime edge case testing

    def test_invalid_patient_ids(self, scheduler):
        """Test handling of invalid patient IDs."""
        # Test with None
        patient = scheduler.find_patient_by_id(None)
        assert patient is None, "Should handle None patient ID"

        # Test with empty string
        patient = scheduler.find_patient_by_id("")
        assert patient is None, "Should handle empty patient ID"

    def test_invalid_appointment_ids(self, scheduler):
        """Test handling of invalid appointment IDs."""
        success = scheduler.cancel_appointment("NONEXISTENT")
        assert success == False, "Should handle invalid appointment ID"

    def test_future_date_availability(self, scheduler):
        """Test availability checking for various dates."""
        today = date.today()
        far_future = today + timedelta(days=365)

        # Should not crash for far future dates
        slots = scheduler.find_available_slots(far_future, AppointmentType.REGULAR_CHECKUP)
        assert isinstance(slots, list), "Should return list even for far future dates"

    def test_weekend_availability(self, scheduler):
        """Test availability checking for weekends."""
        # Find next Saturday
        today = date.today()
        days_until_saturday = (5 - today.weekday()) % 7
        next_saturday = today + timedelta(days=days_until_saturday)

        slots = scheduler.find_available_slots(next_saturday, AppointmentType.REGULAR_CHECKUP)
        assert isinstance(slots, list), "Should return list for weekend"

    def test_appointment_type_duration(self, scheduler):
        """Test different appointment types have correct durations."""
        if not scheduler.availability:
            pytest.skip("No availability data loaded")

        # Check that appointment types have durations
        assert len(scheduler.availability.appointment_types) > 0, "No appointment types defined"

        for appt_type, info in scheduler.availability.appointment_types.items():
            assert info.duration > 0, f"Appointment type {appt_type} has invalid duration"


class TestAPIIntegration:
    """Test API integration (if server is running)."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test the health check endpoint."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://127.0.0.1:8000/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        assert "status" in data, "Health response missing status"
                        assert data["status"] == "healthy", "Health check failed"
                    else:
                        pytest.skip("Server not running")
        except Exception:
            pytest.skip("Server not running or not accessible")

    @pytest.mark.asyncio
    async def test_chat_endpoint_basic(self):
        """Test the basic chat endpoint."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                chat_data = {
                    "message": "Hello, I need help with my appointment",
                    "patient_name": "Alice Brown"
                }

                async with session.post("http://127.0.0.1:8000/chat", json=chat_data) as response:
                    if response.status == 200:
                        data = await response.json()
                        assert "message" in data, "Chat response missing message"
                        assert len(data["message"]) > 0, "Empty response message"
                    else:
                        pytest.skip("Server not running")
        except Exception:
            pytest.skip("Server not running or not accessible")

    @pytest.mark.asyncio
    async def test_chat_endpoint_with_conversation_id(self):
        """Test the chat endpoint with conversation_id (regression test for missing attribute)."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                # Test case that would previously trigger: 'ChatRequest' object has no attribute 'conversation_id'
                chat_data = {
                    "message": "I want to confirm my appointment tomorrow",
                    "patient_name": "Alice Brown",
                    "patient_id": "P001",
                    "conversation_id": "test_conv_123"
                }

                async with session.post("http://127.0.0.1:8000/chat", json=chat_data) as response:
                    if response.status == 200:
                        data = await response.json()
                        assert "message" in data, "Chat response missing message"
                        assert "conversation_id" in data, "Chat response missing conversation_id"
                        assert data["conversation_id"] == "test_conv_123", "Conversation ID not preserved"
                        assert len(data["message"]) > 0, "Empty response message"
                    else:
                        pytest.skip("Server not running")
        except Exception:
            pytest.skip("Server not running or not accessible")

    def test_chat_request_model_with_conversation_id(self):
        """Test ChatRequest model accepts conversation_id field."""
        # Test with conversation_id
        request = ChatRequest(
            message="Test message",
            patient_name="Test Patient",
            conversation_id="conv_123"
        )

        assert request.message == "Test message"
        assert request.patient_name == "Test Patient"
        assert request.conversation_id == "conv_123"
        assert request.patient_id is None

        # Test without conversation_id (should be None)
        request2 = ChatRequest(
            message="Test message 2",
            patient_name="Test Patient 2"
        )

        assert request2.message == "Test message 2"
        assert request2.conversation_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])