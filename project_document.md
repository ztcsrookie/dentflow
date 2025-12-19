# DentFlow — Project Specification Document
*(for Claude / LLM development workflow)*

## 1. Overview

**DentFlow** is a project aimed at developing an **LLM-based scheduling agent** for dental check-ups.  
The agent should simulate how dental clinics contact patients, confirm upcoming appointments, and assist with rescheduling when necessary.

The final system will be implemented as a **local web application**, running entirely inside the `DentFlow` project directory (no public domain, local debugging only).

All operations (code generation, file creation, tests, etc.) must be scoped to the `DentFlow/` folder.

---

## 2. Project Goals

The DentFlow Scheduling Agent should:

1. **Understand patient scheduling scenarios**  
   Including confirmations, cancellations, rescheduling, and follow-up messages.

2. **Generate structured schedule outputs**  
   E.g., JSON or a well-defined table format describing appointment status changes.

3. **Act as an automated assistant**  
   Simulating the role of staff in a dental clinic calling patients before appointments.

4. **Be evaluated on predefined benchmark scenarios**  
   Multiple scripted dialogues should be used to test the agent’s performance.

5. **Be runnable end-to-end**  
   There must be a simple way (via README instructions) to:
   - install dependencies,
   - start the web app,
   - run tests and benchmark scenarios.

---

## 3. Functional Requirements

### 3.1 Core Functions

The agent should be able to:

- Confirm an existing dental appointment  
- Handle appointment cancellation requests  
- Offer alternative time slots based on a scheduling policy  
- Update the appointment record in a structured format  
- Ask clarification questions when necessary  
- Detect when the conversation has reached a natural completion

### 3.2 Scheduling Format (Initial Draft)

The system should output appointment updates in a **structured JSON format**, for example:

```json
{
  "patient_name": "Alice Brown",
  "original_appointment": "2025-01-18 10:00",
  "status": "rescheduled",
  "new_appointment": "2025-01-20 14:00",
  "notes": "Patient requested afternoon slot"
}
Claude should always return two parts:
	1.	The conversational reply (human-readable)
	2.	A structured schedule_update block (machine-readable JSON object)
4. Scenarios for Benchmark Testing

We will prepare a set of benchmark test scenarios to evaluate the scheduling agent. Claude should support running these scenarios programmatically.

All scenario files must be stored in DentFlow/scenarios/.

4.1 Example Scenario A — Simple Confirmation
'''
Patient: Hi, I want to confirm my appointment tomorrow.
'''
Expected result:
→ Respond politely; status becomes “confirmed”.

4.2 Scenario B — Rescheduling
'''
Patient: I can’t make it on Tuesday morning. Can I do Thursday afternoon?
'''
Expected result:
→ Identify the original slot → Offer alternative time slots based on availability → Confirm a new appointment → Produce a corresponding schedule update.

4.3 Scenario C — Cancellation
'''
Patient: Please cancel my appointment for next week.
'''
Expected result:
→ Set status to "cancelled", optionally ask if the patient wants to rebook later.

More scenarios will be added under /DentFlow/scenarios/.

5. Technical Requirements
5.1 Project Structure (inside DentFlow/)

Claude must follow this directory structure (may add files, but not break the layout):
'''
DentFlow/
│
├── README.md                    # User-facing instructions (must be created/maintained by Claude)
├── requirements.txt             # Python dependencies (must be created/maintained by Claude)
│
├── app/
│   ├── server.py                # Backend (FastAPI or similar)
│   ├── ui/
│   │   └── index.html           # Basic web UI for chat interaction
│   └── scheduling/
│       ├── models.py            # Data models (Pydantic, etc.)
│       └── logic.py             # Scheduling logic utilities
│
├── agents/
│   └── scheduler_agent.claude.md   # System prompt for DentFlow scheduler agent
│
├── data/
│   ├── patients.json            # Example patient records
│   ├── appointments.json        # Initial appointment schedule
│   └── availability.json        # Clinic time-slot rules
│
├── scenarios/
│   ├── scenario_A.txt
│   ├── scenario_B.txt
│   ├── scenario_C.txt
│   └── benchmark_runner.py      # Script to run scenarios through the agent
│
└── tests/
    └── test_agent.py            # Automated tests (e.g. pytest) for agent behavior
'''
5.2 Technologies

Language: Python (3.10+ recommended)

Backend Framework: FastAPI (or another modern async web framework)

Frontend: Minimal HTML/JS client to interact with the backend (chat-style UI)

LLM Integration: Claude via the official Python SDK (anthropic) or HTTP calls

Testing: pytest or simple Python scripts under tests/

5.3 Dependencies & requirements.txt

Claude must create and maintain a requirements.txt file in the root DentFlow/ folder.

This file should contain all top-level Python packages needed to:

run the web server

call Claude

run tests

run benchmark scenarios

At minimum, requirements.txt should include entries equivalent to:
'''
fastapi
uvicorn
anthropic
python-dotenv
pydantic
rich
jinja2
httpx
pytest
'''
Claude may add more dependencies as needed but must keep requirements.txt in sync with the codebase.

6. LLM Agent Specification

The DentFlow Scheduler Agent must follow these rules when responding.

6.1 Behavior

Be polite, clear, and professional

Ask clarifying questions when needed

Never invent unavailable time slots beyond defined availability (unless explicitly allowed)

Always output a structured schedule update when the appointment status changes

Handle edge cases such as:

patient not found

no available slot in requested time range

invalid date/time formats

6.2 Output Format

Every response from the agent must contain two sections:

1. Human-readable reply

Example:
'''
Certainly! I can help you reschedule your appointment.
We currently have openings on Thursday at 14:00 or 16:30. Which one would you prefer?
'''

2. Machine-readable schedule update
'''
schedule_update: {
  "patient_name": "Alice Brown",
  "status": "rescheduled",
  "original_appointment": "2025-01-18 10:00",
  "new_appointment": "2025-01-20 14:00",
  "notes": "Rescheduled per patient request"
}
'''
If no update is needed yet (e.g., still clarifying information), schedule_update may have:
'''
schedule_update: {
  "status": "pending",
  "reason": "waiting_for_patient_confirmation"
}
'''
7. Development Workflow (for Claude)

Claude will be used to:

Generate and refine the system prompt in agents/scheduler_agent.claude.md.

Implement backend scheduling logic (app/scheduling/logic.py, models.py).

Implement the web server (app/server.py) and simple UI under app/ui/.

Implement scenario runner in scenarios/benchmark_runner.py.

Implement tests in tests/test_agent.py.

Ensure everything runs end-to-end on a local machine using only:

pip install -r requirements.txt

the commands documented in README.md.

All code and configuration must be created and maintained inside the DentFlow/ directory.

8. Benchmarking & Testing Requirements

Claude must:

1. Provide a way to run all benchmark scenarios via a single command, such as:
'''
python scenarios/benchmark_runner.py
'''

2.Implement basic automated tests (e.g., pytest) to validate:

correct JSON structure for schedule_update

correct handling of simple confirmation / reschedule / cancellation scenarios

robustness against missing or malformed input

3. Ensure that tests can be executed via:
'''
pytest
'''
or a documented alternative (described clearly in README.md).

4. Make sure all tests pass on a clean environment where the user only did:
'''
pip install -r requirements.txt
'''

9. README Requirements

Claude must create and maintain a user-facing README.md at the root of DentFlow/.

This README should, at minimum, include:

1. Project Description

Briefly explain what DentFlow does.

2. Environment Setup

Required Python version (e.g., 3.10+).

Instructions to create and activate a virtualenv/conda env (optional but recommended).

Command to install dependencies:
'''
pip install -r requirements.txt
'''

3.How to Run the Web App

Command to start the server, for example:
'''
uvicorn app.server:app --reload
'''
Which URL to open in the browser (e.g., http://127.0.0.1:8000 or a specific /ui route).

4. How to Use the Web UI

Where to access the chat interface.

5. How to simulate a patient conversation.

6. How to Run Tests

Example:
python scenarios/benchmark_runner.py

7.Configuration Notes

How to set the Claude API key (e.g., .env file with ANTHROPIC_API_KEY=...).

Any environment variables required.

The README is part of the deliverable and must remain up to date whenever Claude adds/removes features or dependencies.

10. Deliverables from Claude

By the end of development, Claude must ensure that:

1. The codebase under DentFlow/ is self-contained and runnable.

2. A clean Python environment can run the project using:
'''
pip install -r requirements.txt
'''

3. The web app can be started using the documented command in README.md.

4. Basic test suite (tests/test_agent.py) passes.

5. Benchmark script(s) under scenarios/ can be executed and produce reasonable logs/outputs.

6. README.md clearly explains how to install, run, and test the project.

7. requirements.txt lists all necessary dependencies and is kept in sync with the actual code.

11. Instructions for Claude

Claude should treat this document as:

The master specification of the DentFlow project.

The source of truth for folder structure, behavior, and deliverables.

The guide for creating and modifying files inside DentFlow/.

Whenever Claude generates or modifies code/files, it must:

Assume the working directory is DentFlow/.

Follow the folder structure defined in Section 5.1.

Follow the agent behavior and output format in Sections 6 and 8.

Maintain README.md and requirements.txt aligned with the current codebase.

Ensure that the project can be set up and run only using the instructions in README.md.

'''

---

你可以直接把这份 md 贴给 Claude 当成“项目说明 / 需求文档”。  
后面你要是想让我再帮你写一版：

- 示例版 `README.md` 草稿  
- 示例 `requirements.txt` 初始内容（按你现在 dentflow 环境量身定制）

我也可以直接给你一套可以立刻用的版本。
''