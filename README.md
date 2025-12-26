# DentFlow — LLM-based Dental Scheduling Agent

**DentFlow** is an intelligent scheduling agent for dental clinics that simulates how staff contact patients, confirm upcoming appointments, and assist with rescheduling when necessary. The system uses LLM technology to provide natural, conversational interactions while maintaining structured appointment management.

## Features

- 🦷 **Appointment Confirmations** - Automatically confirm existing dental appointments
- 📅 **Smart Rescheduling** - Offer alternative time slots based on clinic availability
- ❌ **Cancellation Handling** - Process cancellation requests with follow-up options
- 👤 **Automatic Patient Detection** - Distinguish between existing and new patients
- 🆕 **New Patient Registration** - Collect and register new patient information automatically
- 🔍 **Intelligent Patient Lookup** - Find patients by name, phone, email, or patient ID
- 💬 **Natural Conversations** - Human-like interactions using configurable LLM
- 📊 **Structured Output** - JSON-formatted schedule updates for integration
- 🔧 **Flexible LLM Backend** - Compatible with OpenAI-compatible API endpoints
- 🧪 **Benchmark Testing** - Comprehensive test scenarios for validation
- 🌐 **Web Interface** - Simple chat-style UI for interaction

## Environment Setup

**Requirements:**
- Python 3.10 or higher
- pip package manager

**1. Clone/Download the Project:**
```bash
# If you have this project in a git repository
git clone <repository-url>
cd DentFlow

# If you have the project files directly
cd DentFlow
```

**2. Create Virtual Environment (Recommended):**
```bash
# Using venv
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Using conda (alternative)
conda create -n dentflow python=3.10
conda activate dentflow
```

**3. Install Dependencies:**
```bash
pip install -r requirements.txt
```

**4. Configure Environment Variables:**
Create a `.env` file in the DentFlow root directory:

**Option A: Copy the example file:**
```bash
cp .env.example .env
```

**Option B: Create manually:**
```env
# Required LLM Configuration
LLM_PROVIDER=openai
LLM_MODEL=deepseek-v3.2-exp
LLM_API_KEY=your_key_here
LLM_BASE_URL=https://aiapi.iiis.co:9443/v1

# Optional: Override server settings
# APP_HOST=0.0.0.0
# APP_PORT=8000
# LLM_TIMEOUT=60
```

**Environment Variable Details:**
- `LLM_PROVIDER` - Set to "openai" for OpenAI-compatible APIs
- `LLM_MODEL` - The model name to use (e.g., "deepseek-v3.2-exp")
- `LLM_API_KEY` - Your API key for the chosen LLM provider
- `LLM_BASE_URL` - The base URL for the LLM API endpoint

The server will automatically load environment variables from the `.env` file when it starts.

## How to Run the Web App

**Start the Server:**
```bash
uvicorn app.server:app --reload
```

**Access the Application:**
- Open your browser and navigate to: **http://127.0.0.1:8000**
- The web interface will be available at the root URL

## How to Use the Web UI

1. **Open the Chat Interface** - Navigate to the web app URL
2. **Start a Conversation** - Type messages as if you're a patient calling the clinic

### For Existing Patients:
3. **Example Patient Messages:**
   - "Hi, I want to confirm my appointment tomorrow."
   - "I can't make it on Tuesday morning. Can I do Thursday afternoon?"
   - "Please cancel my appointment for next week."

The agent will automatically identify you using your name, phone number, or email and provide information about your upcoming appointments.

### For New Patients:
3. **Example New Patient Messages:**
   - "Hi, I'm a new patient and I'd like to schedule an appointment."
   - "I've never been to your clinic before, can I book a consultation?"

The agent will guide you through the registration process by collecting:
- Full name
- Phone number
- Email address
- Date of birth
- Insurance information (optional)
- Any notes or special requirements

The agent will respond conversationally and provide structured schedule updates.

## How to Run Tests

**1. Run Automated Tests:**
```bash
pytest
```

**2. Run Benchmark Scenarios:**
```bash
python scenarios/benchmark_runner.py
```

This will execute all test scenarios and show how the agent handles different scheduling situations.

## Project Structure

```
DentFlow/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── .env                        # Environment variables (create this)
│
├── app/
│   ├── server.py               # FastAPI backend server
│   ├── ui/
│   │   └── index.html          # Web chat interface
│   └── scheduling/
│       ├── models.py           # Pydantic data models
│       ├── logic.py            # Scheduling business logic
│       └── patient_repository.py # Patient data management
│
├── agents/
│   └── scheduler_agent.claude.md  # Agent system prompt
│
├── data/
│   ├── patients.json           # Patient records
│   ├── appointments.json       # Appointment schedule
│   ├── availability.json       # Clinic availability rules
│   └── conversations.json      # Conversation history (auto-generated)
│
├── scenarios/
│   ├── scenario_A.txt          # Simple confirmation test
│   ├── scenario_B.txt          # Rescheduling test
│   ├── scenario_C.txt          # Cancellation test
│   └── benchmark_runner.py     # Test execution script
│
└── tests/
    ├── test_agent.py           # Automated test suite
    └── test_persistence_queries.py # Persistence/query checks
```

## Data Storage

DentFlow uses JSON files for persistence (no external database required):

- `data/patients.json` stores patient records
- `data/appointments.json` stores appointment records
- `data/conversations.json` stores chat history for retrieval by conversation ID

Writes are atomic (temp file + rename) to reduce corruption risk.

## Patient Management

### Patient Information Storage

Patient information is stored in `data/patients.json` with the following structure:

```json
{
  "patients": [
    {
      "id": "P001",
      "name": "Alice Brown",
      "phone": "+1-555-0101",
      "email": "alice.brown@email.com",
      "date_of_birth": "1985-03-15",
      "insurance_info": "DentalCare Plus",
      "notes": "Prefers morning appointments, allergic to latex"
    }
  ]
}
```

### Patient Detection and Registration

The system automatically distinguishes between existing and new patients:

1. **Existing Patients**: When a patient provides identifying information (name, phone, email, or patient ID), the system searches `data/patients.json` for matches and loads their appointment history from `data/appointments.json`.

2. **New Patients**: If no match is found, the system guides the patient through registration by collecting required information and automatically appends a new patient record to `data/patients.json` with a unique patient ID (P006, P007, etc.).

3. **Multiple Matches**: If multiple patients match the provided information, the system asks for additional details to resolve the ambiguity.

## API Endpoints

When the server is running, these endpoints are available:

### Chat and Scheduling
- `GET /` - Web chat interface
- `POST /chat` - Send messages to the scheduling agent
- `GET /appointments` - View appointment schedule (supports filters)
- `POST /appointments` - Create a new appointment
- `GET /health` - Health check endpoint

### Patient Management
- `POST /register-patient` - Register a new patient
- `POST /find-patient` - Find patient by name, phone, or email
- `GET /patients` - View patients (supports filters)
- `GET /conversation/{conversation_id}` - Get conversation history
- `GET /conversations` - List conversations (supports filters)

### Appointment Management
- `POST /appointment/{appointment_id}/confirm` - Confirm an appointment
- `POST /appointment/{appointment_id}/cancel` - Cancel an appointment
- `GET /availability` - Get available time slots for a specific date

### Query Parameters (Filters)

**Appointments**
- `patient_id`, `patient_name`, `status`
- `date_from`, `date_to` (YYYY-MM-DD or ISO datetime)
- `keyword` (matches notes, dentist, patient_name)

**Patients**
- `patient_id`, `name`, `phone`, `email`

**Conversations**
- `patient_id`, `patient_name`
- `date_from`, `date_to` (YYYY-MM-DD or ISO datetime)
- `keyword` (matches message content)

### Example Requests

```bash
# Create a patient
curl -X POST http://127.0.0.1:8000/register-patient \
  -H 'Content-Type: application/json' \
  -d '{"name":"Jane Roe","phone":"+1-555-222-3333","email":"jane.roe@email.com","date_of_birth":"1990-02-02"}'

# Create an appointment
curl -X POST http://127.0.0.1:8000/appointments \
  -H 'Content-Type: application/json' \
  -d '{"patient_name":"Jane Roe","datetime":"2025-12-10T10:00:00","type":"regular_checkup","notes":"Initial visit"}'

# Query appointments by date range
curl "http://127.0.0.1:8000/appointments?date_from=2025-12-01&date_to=2025-12-31"

# Fetch conversation history
curl "http://127.0.0.1:8000/conversation/conv_1234567890"
```

## Configuration Notes

### Environment Variables

**Required for LLM Functionality:**
- `LLM_PROVIDER` - LLM provider (currently supports "openai" for OpenAI-compatible APIs)
- `LLM_MODEL` - Model name to use (e.g., "deepseek-v3.2-exp")
- `LLM_API_KEY` - Your API key for the chosen LLM provider
- `LLM_BASE_URL` - Base URL for the LLM API endpoint

**Optional:**
- `APP_HOST` - Server host (default: 0.0.0.0)
- `APP_PORT` - Server port (default: 8000)
- `LLM_TIMEOUT` - LLM API timeout in seconds (default: 60)

### .env File Setup

The application automatically loads environment variables from a `.env` file in the project root. The file should follow this format:

```env
# Required LLM Configuration
LLM_PROVIDER=openai
LLM_MODEL=deepseek-v3.2-exp
LLM_API_KEY=your_actual_api_key_here
LLM_BASE_URL=https://aiapi.iiis.co:9443/v1

# Optional settings
APP_HOST=0.0.0.0
APP_PORT=8000
LLM_TIMEOUT=60
```

**Important:**
- Copy `.env.example` to `.env` and add your actual API key
- Never commit your `.env` file with real credentials to version control
- The application will start with limited functionality (fallback to rule-based responses) if LLM configuration is incomplete

### LLM Provider Configuration

This DentFlow version supports OpenAI-compatible API endpoints. To use with different providers:

1. **DeepSeek API** (Example Configuration):
   ```env
   LLM_PROVIDER=openai
   LLM_MODEL=deepseek-v3.2-exp
   LLM_API_KEY=your_deepseek_api_key
   LLM_BASE_URL=https://aiapi.iiis.co:9443/v1
   ```

2. **OpenAI API**:
   ```env
   LLM_PROVIDER=openai
   LLM_MODEL=gpt-4
   LLM_API_KEY=your_openai_api_key
   LLM_BASE_URL=https://api.openai.com/v1
   ```

3. **Custom OpenAI-Compatible API**:
   ```env
   LLM_PROVIDER=openai
   LLM_MODEL=your_custom_model
   LLM_API_KEY=your_custom_api_key
   LLM_BASE_URL=https://your-custom-endpoint.com/v1
   ```

## Example Agent Response Format

The agent always provides two parts:

**1. Human-readable conversation:**
```
Certainly! I can help you reschedule your appointment.
We currently have openings on Thursday at 14:00 or 16:30. Which one would you prefer?
```

**2. Machine-readable schedule update:**
```json
{
  "patient_name": "Alice Brown",
  "status": "rescheduled",
  "original_appointment": "2025-01-18 10:00",
  "new_appointment": "2025-01-20 14:00",
  "notes": "Rescheduled per patient request"
}
```

## Troubleshooting

**Common Issues:**

1. **ModuleNotFoundError:**
   ```bash
   # Make sure you're in the DentFlow directory and have installed requirements
   pip install -r requirements.txt
   ```

2. **API Key Error:**
   ```bash
   # Check your .env file contains valid LLM configuration
   # Ensure LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL are set correctly
   # Ensure the file is in the DentFlow root directory
   ```

3. **Port Already in Use:**
   ```bash
   # Either stop the other process or use a different port
   uvicorn app.server:app --port 8080
   ```

4. **Invalid Date Format in Query Filters:**
   ```bash
   # Use YYYY-MM-DD or full ISO datetime
   /appointments?date_from=2025-12-01
   /appointments?date_from=2025-12-01T09:00:00
   ```

## Development

**Adding New Scenarios:**
1. Create new scenario files in `scenarios/` folder
2. Update `benchmark_runner.py` to include new scenarios
3. Add corresponding tests in `tests/test_agent.py`

**Modifying Agent Behavior:**
- Edit the system prompt in `agents/scheduler_agent.claude.md`
- Update scheduling logic in `app/scheduling/logic.py`

## License

This project is for educational and demonstration purposes. Please ensure compliance with your chosen LLM provider's API terms of service when using in production.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the test scenarios for expected behavior patterns
3. Verify your LLM configuration (API key, base URL, model) is properly set in the .env file
4. Check the health endpoint (`/health`) to see if LLM configuration is detected correctly
