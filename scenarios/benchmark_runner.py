#!/usr/bin/env python3
"""
DentFlow Benchmark Runner

This script runs all test scenarios through the scheduling agent and generates
performance reports to evaluate the agent's behavior against expected outcomes.
"""

import os
import sys
import json
import time
import asyncio
import aiohttp
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
from rich.text import Text

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the parent directory to sys.path for imports
sys.path.append(str(Path(__file__).parent.parent))

from app.scheduling.models import BenchmarkScenario, BenchmarkResult, AppointmentStatus
from app.scheduling.logic import SchedulingLogic


class BenchmarkRunner:
    def __init__(self, api_base_url: str = "http://127.0.0.1:8000"):
        self.api_base_url = api_base_url
        self.console = Console()
        self.scheduler = SchedulingLogic()
        self.results: List[BenchmarkResult] = []

    def load_scenarios(self, scenarios_dir: str = None) -> List[BenchmarkScenario]:
        """Load all scenario files from the scenarios directory."""
        if scenarios_dir is None:
            scenarios_dir = Path(__file__).parent

        scenarios = []
        scenario_files = list(Path(scenarios_dir).glob("scenario_*.txt"))

        if not scenario_files:
            self.console.print("[red]No scenario files found in the scenarios directory.[/red]")
            return scenarios

        self.console.print(f"Loading scenarios from {scenarios_dir}...")

        for scenario_file in scenario_files:
            try:
                with open(scenario_file, 'r') as f:
                    scenario_data = json.load(f)

                # Convert expected_status string to enum if present
                if 'expected_status' in scenario_data and scenario_data['expected_status']:
                    try:
                        scenario_data['expected_status'] = AppointmentStatus(scenario_data['expected_status'])
                    except ValueError:
                        scenario_data['expected_status'] = None

                scenario = BenchmarkScenario(**scenario_data)
                scenarios.append(scenario)
                self.console.print(f"  ✓ Loaded {scenario.name} from {scenario_file.name}")

            except Exception as e:
                self.console.print(f"  ✗ Error loading {scenario_file.name}: {e}")

        return scenarios

    async def setup_scenario(self, scenario: BenchmarkScenario) -> bool:
        """Set up the initial data for a scenario."""
        if not scenario.setup_data:
            return True

        try:
            setup = scenario.setup_data

            # Handle ensure_appointment_exists
            if "ensure_appointment_exists" in setup:
                appt_data = setup["ensure_appointment_exists"]

                # Find or create patient
                patient = self.scheduler.find_patient_by_id(appt_data.get("patient_id"))
                if not patient and appt_data.get("patient_name"):
                    patient = self.scheduler.find_patient_by_name(appt_data["patient_name"])

                if not patient:
                    self.console.print(f"[yellow]Warning: Patient {appt_data.get('patient_id', appt_data.get('patient_name'))} not found for scenario {scenario.id}[/yellow]")
                    return False

                # Create or update appointment
                appointment_id = f"{scenario.id}_test"
                from datetime import datetime
                from app.scheduling.models import Appointment, AppointmentType

                appointment = Appointment(
                    id=appointment_id,
                    patient_id=appt_data["patient_id"],
                    patient_name=patient.name,
                    datetime=datetime.fromisoformat(appt_data["datetime"]),
                    duration=60,
                    type=AppointmentType(appt_data["type"]),
                    status=AppointmentStatus(appt_data["status"])
                )

                self.scheduler.appointments[appointment_id] = appointment

            # Handle ensure_patient_not_exists
            if "ensure_patient_not_exists" in setup:
                patient_data = setup["ensure_patient_not_exists"]
                patient_name = patient_data["name"]

                # Remove patient if they exist (for testing purposes)
                patient = self.scheduler.find_patient_by_name(patient_name)
                if patient:
                    # In a real system, we might want to handle this differently
                    self.console.print(f"[yellow]Warning: Patient {patient_name} already exists for scenario {scenario.id}[/yellow]")

            return True

        except Exception as e:
            self.console.print(f"[red]Error setting up scenario {scenario.id}: {e}[/red]")
            return False

    async def run_single_scenario(self, session: aiohttp.ClientSession, scenario: BenchmarkScenario) -> BenchmarkResult:
        """Run a single scenario and return the result."""
        start_time = time.time()

        try:
            # Set up the scenario
            if not await self.setup_scenario(scenario):
                return BenchmarkResult(
                    scenario_id=scenario.id,
                    passed=False,
                    actual_response="Scenario setup failed",
                    execution_time=time.time() - start_time
                )

            # Prepare the chat request
            chat_request = {
                "message": scenario.patient_message,
                "patient_id": getattr(scenario, 'patient_id', None),
                "patient_name": getattr(scenario, 'patient_name', None)
            }

            # Make the API call
            async with session.post(f"{self.api_base_url}/chat", json=chat_request) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return BenchmarkResult(
                        scenario_id=scenario.id,
                        passed=False,
                        actual_response=f"API call failed with status {response.status}: {error_text}",
                        execution_time=time.time() - start_time
                    )

                response_data = await response.json()

            actual_response = response_data.get("message", "")
            schedule_update = response_data.get("schedule_update")

            # Evaluate the result
            passed, evaluation_details = await self.evaluate_scenario(scenario, actual_response, schedule_update)

            return BenchmarkResult(
                scenario_id=scenario.id,
                passed=passed,
                actual_response=actual_response,
                actual_schedule_update=schedule_update,
                expected_vs_actual=evaluation_details,
                execution_time=time.time() - start_time
            )

        except Exception as e:
            return BenchmarkResult(
                scenario_id=scenario.id,
                passed=False,
                actual_response=f"Error running scenario: {str(e)}",
                execution_time=time.time() - start_time
            )

    async def evaluate_scenario(self, scenario: BenchmarkScenario, response: str, schedule_update: Dict) -> Tuple[bool, str]:
        """Evaluate if the scenario response meets the expected criteria."""
        evaluation_details = []
        passed = True

        # Check expected response keywords
        if scenario.expected_response_keywords:
            response_lower = response.lower()
            missing_keywords = []
            for keyword in scenario.expected_response_keywords:
                if keyword.lower() not in response_lower:
                    missing_keywords.append(keyword)

            if missing_keywords:
                passed = False
                evaluation_details.append(f"Missing keywords: {missing_keywords}")
            else:
                evaluation_details.append("✓ All expected keywords found")

        # Check schedule update status
        if scenario.expected_status:
            if not schedule_update:
                passed = False
                evaluation_details.append("✗ No schedule update returned")
            elif schedule_update.get("status") != scenario.expected_status.value:
                passed = False
                evaluation_details.append(f"✗ Expected status {scenario.expected_status.value}, got {schedule_update.get('status')}")
            else:
                evaluation_details.append(f"✓ Correct status: {schedule_update.get('status')}")

        # Check success criteria
        if scenario.success_criteria:
            criteria = scenario.success_criteria

            # Check response_contains_keywords
            if criteria.get("response_contains_keywords"):
                if scenario.expected_response_keywords:
                    all_found = all(kw.lower() in response.lower() for kw in scenario.expected_response_keywords)
                    if all_found:
                        evaluation_details.append("✓ Response contains expected keywords")
                    else:
                        passed = False
                        evaluation_details.append("✗ Response missing expected keywords")

            # Check schedule_update_status
            if "schedule_update_status" in criteria:
                expected_status = criteria["schedule_update_status"]
                if not schedule_update or schedule_update.get("status") != expected_status:
                    passed = False
                    evaluation_details.append(f"✗ Schedule update status mismatch")
                else:
                    evaluation_details.append(f"✓ Schedule update status correct: {expected_status}")

            # Check offers_alternatives
            if criteria.get("offers_alternatives"):
                alternatives_keywords = ["alternative", "option", "would you prefer", "available", "choose", "selection"]
                has_alternatives = any(kw in response.lower() for kw in alternatives_keywords)
                if has_alternatives:
                    evaluation_details.append("✓ Offers alternatives")
                else:
                    passed = False
                    evaluation_details.append("✗ Does not offer alternatives")

            # Check mentions_thursday
            if criteria.get("mentions_thursday"):
                if "thursday" in response.lower():
                    evaluation_details.append("✓ Mentions Thursday")
                else:
                    passed = False
                    evaluation_details.append("✗ Does not mention Thursday")

            # Check appointment_datetime_matches
            if "appointment_datetime_matches" in criteria:
                expected_datetime = criteria["appointment_datetime_matches"]
                if schedule_update and (
                    schedule_update.get("original_appointment") == expected_datetime or
                    schedule_update.get("new_appointment") == expected_datetime
                ):
                    evaluation_details.append("✓ Appointment datetime matches")
                else:
                    passed = False
                    evaluation_details.append("✗ Appointment datetime mismatch")

        return passed, "; ".join(evaluation_details)

    async def run_all_scenarios(self, scenarios: List[BenchmarkScenario]) -> List[BenchmarkResult]:
        """Run all scenarios and return the results."""
        self.console.print(f"\n[yellow]Running {len(scenarios)} scenarios...[/yellow]")

        async with aiohttp.ClientSession() as session:
            tasks = []
            with Progress() as progress:
                task = progress.add_task("Running scenarios...", total=len(scenarios))

                for scenario in scenarios:
                    coro = self.run_single_scenario(session, scenario)
                    task_coro = self._run_with_progress(coro, scenario, progress, task)
                    tasks.append(task_coro)

                results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and convert to BenchmarkResults
        final_results = []
        for result in results:
            if isinstance(result, Exception):
                self.console.print(f"[red]Error during scenario execution: {result}[/red]")
            else:
                final_results.append(result)

        return final_results

    async def _run_with_progress(self, coro, scenario, progress, task):
        """Helper to run a scenario with progress tracking."""
        try:
            result = await coro
            progress.advance(task)
            return result
        except Exception as e:
            progress.advance(task)
            raise e

    def generate_report(self, results: List[BenchmarkResult]) -> None:
        """Generate and display a comprehensive benchmark report."""
        if not results:
            self.console.print("[red]No results to report[/red]")
            return

        # Calculate statistics
        total_scenarios = len(results)
        passed_scenarios = sum(1 for r in results if r.passed)
        failed_scenarios = total_scenarios - passed_scenarios
        pass_rate = (passed_scenarios / total_scenarios) * 100
        avg_execution_time = sum(r.execution_time for r in results) / total_scenarios

        # Summary panel
        summary_text = f"""
Total Scenarios: {total_scenarios}
Passed: {passed_scenarios}
Failed: {failed_scenarios}
Pass Rate: {pass_rate:.1f}%
Average Execution Time: {avg_execution_time:.3f}s
        """
        self.console.print(Panel(summary_text.strip(), title="📊 Benchmark Summary", border_style="blue"))

        # Detailed results table
        table = Table(title="Scenario Results")
        table.add_column("Scenario ID", style="cyan", no_wrap=True)
        table.add_column("Status", style="green")
        table.add_column("Execution Time", style="yellow", justify="right")
        table.add_column("Details", style="white")

        for result in results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            status_style = "green" if result.passed else "red"

            # Truncate details if too long
            details = result.expected_vs_actual or "No evaluation details"
            if len(details) > 80:
                details = details[:77] + "..."

            table.add_row(
                result.scenario_id,
                f"[{status_style}]{status}[/{status_style}]",
                f"{result.execution_time:.3f}s",
                details
            )

        self.console.print(table)

        # Failed scenarios details
        failed_results = [r for r in results if not r.passed]
        if failed_results:
            self.console.print("\n[red]Failed Scenarios Details:[/red]")
            for result in failed_results:
                self.console.print(f"\n[bold]Scenario {result.scenario_id}:[/bold]")
                self.console.print(f"  Response: {result.actual_response[:200]}...")
                if result.expected_vs_actual:
                    self.console.print(f"  Issues: {result.expected_vs_actual}")

    def save_results(self, results: List[BenchmarkResult], output_file: str = None) -> None:
        """Save benchmark results to a JSON file."""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"benchmark_results_{timestamp}.json"

        results_data = {
            "timestamp": datetime.now().isoformat(),
            "total_scenarios": len(results),
            "passed_scenarios": sum(1 for r in results if r.passed),
            "failed_scenarios": sum(1 for r in results if not r.passed),
            "pass_rate": (sum(1 for r in results if r.passed) / len(results)) * 100,
            "average_execution_time": sum(r.execution_time for r in results) / len(results),
            "results": [r.dict() for r in results]
        }

        try:
            with open(output_file, 'w') as f:
                json.dump(results_data, f, indent=2, default=str)
            self.console.print(f"\n[green]Results saved to {output_file}[/green]")
        except Exception as e:
            self.console.print(f"[red]Error saving results: {e}[/red]")


async def main():
    """Main function to run the benchmark."""
    parser = argparse.ArgumentParser(description="Run DentFlow benchmark scenarios")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--scenarios-dir", help="Scenarios directory path")
    parser.add_argument("--output", help="Output file for results")
    parser.add_argument("--scenario", help="Run specific scenario by ID")

    args = parser.parse_args()

    console = Console()
    console.print("[bold blue]🦷 DentFlow Benchmark Runner[/bold blue]")

    # Initialize benchmark runner
    runner = BenchmarkRunner(args.url)

    # Load scenarios
    scenarios = runner.load_scenarios(args.scenarios_dir)
    if not scenarios:
        console.print("[red]No scenarios loaded. Exiting.[/red]")
        return

    # Filter specific scenario if requested
    if args.scenario:
        scenarios = [s for s in scenarios if s.id == args.scenario]
        if not scenarios:
            console.print(f"[red]Scenario {args.scenario} not found.[/red]")
            return

    # Run scenarios
    try:
        results = await runner.run_all_scenarios(scenarios)

        # Generate report
        runner.generate_report(results)

        # Save results
        runner.save_results(results, args.output)

        # Exit with appropriate code
        failed_count = sum(1 for r in results if not r.passed)
        sys.exit(failed_count)

    except KeyboardInterrupt:
        console.print("\n[yellow]Benchmark interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Benchmark error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())