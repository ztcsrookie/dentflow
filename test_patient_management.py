#!/usr/bin/env python3
"""
Test script to demonstrate the patient management feature.
This script shows how the system distinguishes between existing and new patients.
"""

import sys
import os
sys.path.append('.')

from app.scheduling.patient_repository import PatientRepository
from app.scheduling.models import PatientRegistrationRequest
from datetime import datetime


def test_existing_patient_workflow():
    """Test the workflow for an existing patient."""
    print("=== Testing Existing Patient Workflow ===")

    repo = PatientRepository()

    # Simulate a patient calling in
    patient_name = "Alice Brown"

    print(f"Patient identifies as: {patient_name}")

    # System looks up the patient
    result = repo.find_patient_by_identifiers(name=patient_name)

    if result.is_confident_match():
        patient = result.patient
        print(f"✓ Found patient: {patient.name} (ID: {patient.id})")
        print(f"  Phone: {patient.phone}")
        print(f"  Email: {patient.email}")

        # Get their appointments
        appointments = repo.get_upcoming_appointments(patient)
        print(f"  Upcoming appointments: {len(appointments)}")

        for appt in appointments:
            print(f"    - {appt.datetime.strftime('%Y-%m-%d %H:%M')} ({appt.type.value})")

        print("✓ Existing patient workflow completed successfully")
        return True
    else:
        print("✗ Failed to find existing patient")
        return False


def test_new_patient_workflow():
    """Test the workflow for a new patient registration."""
    print("\n=== Testing New Patient Workflow ===")

    repo = PatientRepository()

    # Simulate a new patient calling in
    new_patient_name = "John Doe"
    print(f"Patient identifies as: {new_patient_name}")

    # System looks up the patient
    result = repo.find_patient_by_identifiers(name=new_patient_name)

    if result.is_new_patient:
        print("✓ Identified as new patient")
        print(f"  Missing fields: {result.missing_fields}")

        # Collect patient information
        patient_data = {
            "name": "John Doe",
            "phone": "+1-555-555-0123",
            "email": "john.doe@email.com",
            "date_of_birth": "1985-06-15",
            "insurance_info": "HealthCare Plus",
            "notes": "First time patient, referred by friend"
        }

        # Validate the data
        is_valid, errors = repo.validate_patient_data(patient_data)

        if is_valid:
            print("✓ Patient data validation passed")

            # Create the patient
            date_of_birth = datetime.fromisoformat(patient_data["date_of_birth"]).date()
            patient = repo.create_patient(
                name=patient_data["name"],
                phone=patient_data["phone"],
                email=patient_data["email"],
                date_of_birth=date_of_birth,
                insurance_info=patient_data.get("insurance_info"),
                notes=patient_data.get("notes")
            )

            print(f"✓ Created new patient: {patient.name} (ID: {patient.id})")

            # Verify the patient can be found
            verify_result = repo.find_patient_by_identifiers(name=patient.name)
            if verify_result.is_confident_match():
                print("✓ New patient can be found in system")
                print("✓ New patient workflow completed successfully")
                return True
            else:
                print("✗ Failed to find newly created patient")
                return False
        else:
            print(f"✗ Patient data validation failed: {errors}")
            return False
    else:
        print("✗ Failed to identify as new patient")
        return False


def test_multiple_match_workflow():
    """Test the workflow when multiple patients match."""
    print("\n=== Testing Multiple Match Workflow ===")

    repo = PatientRepository()

    # Create a scenario with similar names
    # First, let's check if we have patients with similar names
    patients = repo.get_all_patients()

    # Look for patients with "John" in the name
    john_patients = [p for p in patients if "john" in p.name.lower()]

    if len(john_patients) > 1:
        print(f"Found {len(john_patients)} patients with 'John' in name:")
        for p in john_patients:
            print(f"  - {p.name} ({p.phone}, {p.email})")

        # Simulate search with ambiguous name
        result = repo.find_patient_by_identifiers(name="John")

        if result.multiple_matches:
            print(f"✓ Correctly identified multiple matches: {len(result.multiple_matches)}")
            print("✓ Multiple match workflow completed successfully")
            return True
        else:
            print("✗ Failed to identify multiple matches")
            return False
    else:
        print("Not enough 'John' patients to test multiple match scenario")
        print("✓ Multiple match test skipped (no ambiguous data)")
        return True


def main():
    """Run all test scenarios."""
    print("DentFlow Patient Management Feature Test")
    print("=" * 50)

    results = []

    # Test existing patient
    results.append(test_existing_patient_workflow())

    # Test new patient registration
    results.append(test_new_patient_workflow())

    # Test multiple matches
    results.append(test_multiple_match_workflow())

    print("\n" + "=" * 50)
    print("Test Summary:")
    print(f"Passed: {sum(results)}/{len(results)}")

    if all(results):
        print("🎉 All tests passed! Patient management feature is working correctly.")
    else:
        print("❌ Some tests failed. Please review the implementation.")

    return all(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)