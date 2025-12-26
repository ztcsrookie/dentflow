import os
import re
import json
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

from .scheduling.models import (
    ChatRequest, ChatResponse, ScheduleUpdate, AppointmentStatus, AppointmentType,
    Appointment, AppointmentCreateRequest, Patient, PatientRegistrationRequest
)
from .scheduling.logic import SchedulingLogic
from .scheduling.patient_repository import PatientRepository, PatientLookupResult


# Initialize FastAPI app
app = FastAPI(
    title="DentFlow Scheduling API",
    description="LLM-based dental scheduling agent API",
    version="1.0.0"
)

# Set up templates and static files
app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")
templates = Jinja2Templates(directory="app/ui")


# Initialize scheduling logic and patient repository
scheduler = SchedulingLogic()
patient_repo = PatientRepository()

# File paths for persistence
APPOINTMENTS_FILE = Path("data") / "appointments.json"
CONVERSATIONS_FILE = Path("data") / "conversations.json"


def persist_appointment_from_schedule_update(
    patient: Optional["Patient"],
    update: "ScheduleUpdate",
) -> None:
    """
    根据 ScheduleUpdate 和当前识别的 patient，把预约变化写入 appointments.json。
    兼容新建、取消、确认、改期场景。
    """
    try:
        appointments = patient_repo.get_all_appointments()

        patient_id = patient.id if patient is not None else None
        patient_name = patient.name if patient is not None else update.patient_name

        def _to_datetime(value: Any) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))

        def _match_patient(appt: Appointment) -> bool:
            if patient_id and appt.patient_id == patient_id:
                return True
            if patient_name and appt.patient_name == patient_name:
                return True
            return False

        status = update.status
        if isinstance(status, AppointmentStatus):
            status_value = status.value
        else:
            status_value = str(status)

        original_dt = _to_datetime(update.original_appointment)
        new_dt = _to_datetime(update.new_appointment)

        target_appt = None
        if original_dt:
            for appt in appointments:
                if _match_patient(appt) and appt.datetime == original_dt:
                    target_appt = appt
                    break

        if target_appt:
            target_appt.status = AppointmentStatus(status_value)
            if new_dt:
                target_appt.datetime = new_dt
            if update.notes:
                target_appt.notes = update.notes
            patient_repo.add_or_update_appointment(target_appt)
            scheduler.reload_appointments()
            print(f"[DEBUG] Updated appointment {target_appt.id} for patient {patient_name}")
            return

        if not new_dt:
            print("[DEBUG] persist_appointment_from_schedule_update: no new_appointment and no match, skipping")
            return

        max_id_num = 0
        for appt in appointments:
            appt_id = appt.id
            if isinstance(appt_id, str) and appt_id.startswith("A"):
                try:
                    n = int(appt_id[1:])
                    max_id_num = max(max_id_num, n)
                except ValueError:
                    continue
        new_id = f"A{max_id_num + 1:03d}"

        notes = update.notes or ""
        appt_type = "regular_checkup"
        notes_lower = notes.lower()
        if "初诊" in notes or "首次" in notes or "consult" in notes_lower:
            appt_type = "initial_consultation"
        elif "复查" in notes or "复诊" in notes or "follow" in notes_lower:
            appt_type = "follow_up"

        duration = 60
        if "90" in notes or "一个半小时" in notes:
            duration = 90

        dentist = "Dr. Sarah Chen"

        new_appt = Appointment(
            id=new_id,
            patient_id=patient_id or "UNKNOWN",
            patient_name=patient_name or "Unknown Patient",
            datetime=new_dt,
            duration=duration,
            type=AppointmentType(appt_type),
            status=AppointmentStatus(status_value),
            notes=notes or "Scheduled via chat assistant",
            dentist=dentist,
        )

        patient_repo.add_or_update_appointment(new_appt)
        scheduler.reload_appointments()
        print(f"[DEBUG] Persisted new appointment {new_id} for patient {patient_name} to {APPOINTMENTS_FILE}")
    except Exception as e:
        print(f"[DEBUG] Error persisting appointment from schedule_update: {e}")

# Initialize LLM client with custom configuration
llm_client = None
llm_model = None

def initialize_llm_client():
    """Initialize LLM client based on environment configuration."""
    global llm_client, llm_model

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model_name = os.getenv("LLM_MODEL")

    if api_key and base_url and model_name:
        try:
            llm_client = OpenAI(api_key=api_key, base_url=base_url)
            llm_model = model_name
            print(f"LLM client initialized with model: {model_name}")
            print(f"Base URL: {base_url}")
        except Exception as e:
            print(f"Failed to initialize LLM client: {e}")
            llm_client = None
            llm_model = None
    else:
        print("LLM configuration incomplete. Missing required environment variables.")
        llm_client = None
        llm_model = None

# Initialize the client
initialize_llm_client()

# Load system prompt
SYSTEM_PROMPT = ""
try:
    with open("agents/scheduler_agent.claude.md", "r") as f:
        SYSTEM_PROMPT = f.read()
        # print(SYSTEM_PROMPT)
except Exception as e:
    print(f"Warning: Could not load system prompt: {e}")
    SYSTEM_PROMPT = "You are a dental clinic scheduling assistant."

def load_conversations_from_file() -> Tuple[Dict[str, List[Dict]], Dict[str, Dict[str, Any]]]:
    """Load conversations from disk for basic persistence."""
    conversations_data: Dict[str, List[Dict]] = {}
    meta_data: Dict[str, Dict[str, Any]] = {}
    if not CONVERSATIONS_FILE.exists():
        return conversations_data, meta_data
    try:
        with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for item in raw.get("conversations", []):
            conv_id = item.get("conversation_id")
            if not conv_id:
                continue
            conversations_data[conv_id] = item.get("messages", [])
            meta_data[conv_id] = {
                "patient_id": item.get("patient_id"),
                "patient_name": item.get("patient_name"),
            }
    except Exception as e:
        print(f"[DEBUG] Error loading conversations file: {e}")
    return conversations_data, meta_data


def save_conversations_to_file() -> None:
    """Persist in-memory conversations to disk."""
    try:
        CONVERSATIONS_FILE.parent.mkdir(exist_ok=True)
        payload = {"conversations": []}
        for conv_id, messages in conversations.items():
            meta = conversation_meta.get(conv_id, {})
            payload["conversations"].append({
                "conversation_id": conv_id,
                "patient_id": meta.get("patient_id"),
                "patient_name": meta.get("patient_name"),
                "messages": messages,
            })
        temp_file = CONVERSATIONS_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        temp_file.replace(CONVERSATIONS_FILE)
    except Exception as e:
        print(f"[DEBUG] Error saving conversations file: {e}")


def record_conversation_exchange(conversation_id: str, user_text: str, assistant_text: str) -> None:
    """Append a user/assistant exchange to the conversation history and persist."""
    user_message = {
        "role": "user",
        "content": user_text,
        "timestamp": datetime.now().isoformat(),
    }
    assistant_message = {
        "role": "assistant",
        "content": assistant_text,
        "timestamp": datetime.now().isoformat(),
    }
    conversations[conversation_id].append(user_message)
    conversations[conversation_id].append(assistant_message)
    save_conversations_to_file()


# Global conversation storage (in production, use a proper database)
conversations, conversation_meta = load_conversations_from_file()


class ConversationMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[datetime] = None


class ChatHistoryRequest(BaseModel):
    conversation_id: Optional[str] = None
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None


def extract_schedule_update_from_response(response_text: str) -> Optional[Dict]:
    """Extract the schedule_update JSON from Claude's response."""
    # Look for schedule_update: { ... }
    pattern = r"schedule_update:\s*({.*?})"
    match = re.search(pattern, response_text, re.DOTALL)

    if match:
        try:
            schedule_data = json.loads(match.group(1))
            return schedule_data
        except json.JSONDecodeError:
            print(f"Failed to parse schedule_update JSON: {match.group(1)}")
            return None
    return None


def clean_response_text(response_text: str) -> str:
    """Remove the schedule_update JSON block from the response text."""
    # Remove the schedule_update block
    pattern = r"schedule_update:\s*({.*?})"
    cleaned = re.sub(pattern, "", response_text, flags=re.DOTALL)
    # Clean up any extra whitespace
    return cleaned.strip()


def call_llm_for_scheduling(
    message: str,
    conversation_history: List[Dict],
    patient_context: Optional[Dict] = None
) -> tuple[str, Optional[Dict]]:
    """Call LLM API for scheduling assistance using custom endpoint."""
    print(f"[DEBUG] call_llm_for_scheduling called with message: {message[:50]}...")
    print(f"[DEBUG] LLM client available: {llm_client is not None}")
    print(f"[DEBUG] LLM model available: {llm_model is not None}")

    # If LLM client or model is not configured, fall back to basic scheduling logic
    if not llm_client or not llm_model:
        print(f"[DEBUG] LLM not configured, falling back to basic scheduling...")
        return handle_basic_scheduling(message, patient_context)

    # Build messages for LLM
    messages = []

    # Add system message first
    messages.append({
        "role": "system",
        "content": SYSTEM_PROMPT
    })

    # Add conversation history (excluding system messages)
    for msg in conversation_history[-10:]:  # Keep last 10 messages
        if msg.get("role") in ["user", "assistant"]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    # Add current message
    current_message = message
    if patient_context:
        context_info = f"\n\nCurrent Patient Context:\n{json.dumps(patient_context, indent=2, default=str)}"
        current_message += context_info

    messages.append({
        "role": "user",
        "content": current_message
    })

    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=messages,
            max_tokens=2000,
            temperature=0.7
        )

        response_text = response.choices[0].message.content
        schedule_update = extract_schedule_update_from_response(response_text)
        clean_response = clean_response_text(response_text)

        return clean_response, schedule_update

    except Exception as e:
        print(f"Error calling LLM API: {e}")
        return "I'm having trouble connecting to our scheduling system right now. Please try again later.", None


def handle_basic_scheduling(message: str, patient_context: Optional[Dict] = None) -> tuple[str, Optional[Dict]]:
    """Fallback basic scheduling logic when LLM is unavailable."""
    print(f"[DEBUG] handle_basic_scheduling called with message: {message[:50]}...")
    print(f"[DEBUG] Patient context: {patient_context}")

    chat_request = ChatRequest(
        message=message,
        patient_id=patient_context.get("patient_id") if patient_context else None,
        patient_name=patient_context.get("patient_name") if patient_context else None
    )
    print(f"[DEBUG] Created ChatRequest, calling scheduler.process_patient_request...")

    response_text, schedule_update = scheduler.process_patient_request(chat_request)
    print(f"[DEBUG] Scheduler response received, schedule_update type: {type(schedule_update)}")

    if schedule_update:
        print(f"[DEBUG] Converting schedule_update to dict...")
        return response_text, schedule_update.dict()
    else:
        print(f"[DEBUG] No schedule_update to convert")
        return response_text, None

def parse_patient_info_from_message(text: str) -> Dict[str, Any]:
    """Parse basic patient registration information from a free-text message."""
    data: Dict[str, Any] = {
        "name": None,
        "phone": None,
        "email": None,
        "date_of_birth": None,
        "insurance_info": None,
    }

    def try_fill_from_tokens(tokens: List[str]) -> None:
        """Best-effort extraction when user sends comma/space-separated info."""
        remaining = []
        for token in tokens:
            if not token:
                continue
            if not data["email"] and re.search(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9_.-]+", token):
                data["email"] = token
                continue
            if not data["date_of_birth"] and re.search(r"\d{4}-\d{2}-\d{2}", token):
                data["date_of_birth"] = token
                continue
            if not data["phone"]:
                digits = re.sub(r"\D", "", token)
                if len(digits) >= 7:
                    data["phone"] = digits
                    continue
            remaining.append(token)
        if not data["name"] and remaining:
            data["name"] = remaining[0]

    # 尝试解析姓名（如“我叫老张”、“我的名字是老张”、“姓名：老张”）
    name_match = re.search(r"(我叫|我的名字是|姓名[:：]?)\s*([^\s，。,]+)", text)
    if name_match:
        data["name"] = name_match.group(2).strip()

    # 尝试解析电话（如“电话是123456789”）
    phone_match = re.search(r"(电话|手机号|手机号码)[是:： ]*([0-9\- +]{6,})", text)
    if phone_match:
        digits = re.sub(r"\D", "", phone_match.group(2))
        data["phone"] = digits
    else:
        # 兜底：文本里出现的第一段 ≥7 位数字
        fallback_phone = re.search(r"(\d{7,})", text)
        if fallback_phone:
            data["phone"] = fallback_phone.group(1)

    # 尝试解析邮箱
    email_match = re.search(r"([A-Za-z0-9_.+-]+@[A-Za-z0-9_.-]+)", text)
    if email_match:
        data["email"] = email_match.group(1).strip()

    # 尝试解析生日 YYYY-MM-DD
    dob_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if dob_match:
        data["date_of_birth"] = dob_match.group(1)

    # 尝试解析保险信息（“保险 xxx”）
    insurance_match = re.search(r"(保险|insurance)[是:： ]*([^\n，。]+)", text, re.IGNORECASE)
    if insurance_match:
        data["insurance_info"] = insurance_match.group(2).strip()

    # 兜底：按逗号/空白分隔的字段（如“老张，18888888888，cs@126.com，2000-01-01”）
    if not (data["name"] and data["phone"] and data["email"] and data["date_of_birth"]):
        tokens = re.split(r"[，,;\n]+", text)
        tokens = [t.strip() for t in tokens if t.strip()]
        if len(tokens) >= 2:
            try_fill_from_tokens(tokens)

    return data

def get_or_identify_patient(chat_request: ChatRequest) -> Tuple[Optional[Patient], Optional[str]]:
    """
    Identify patient from chat request and return patient and any special handling needed.
    Returns tuple of (patient, special_action) where special_action can be:
    - None: normal flow
    - "new_patient_registration": need to collect new patient info
    - "multiple_matches": need to disambiguate between multiple patients
    """
    # First, check if this conversation already has an identified patient
    if chat_request.conversation_id and chat_request.conversation_id in conversation_meta:
        meta = conversation_meta[chat_request.conversation_id]
        patient_id = meta.get("patient_id")
        if patient_id:
            try:
                # 从仓库里拿这个 patient
                for p in patient_repo.get_all_patients():
                    if p.id == patient_id:
                        return p, None
            except Exception as e:
                print(f"[DEBUG] Error retrieving patient from conversation meta: {e}")

    # Handle explicit new patient registration
    if chat_request.is_new_patient_registration and chat_request.patient_registration_data:
        try:
            # Validate patient data
            patient_data = chat_request.patient_registration_data.dict()
            is_valid, errors = patient_repo.validate_patient_data(patient_data)

            if not is_valid:
                return None, f"validation_error: {', '.join(errors)}"

            # Create new patient
            date_of_birth = datetime.fromisoformat(patient_data["date_of_birth"]).date()
            patient = patient_repo.create_patient(
                name=patient_data["name"],
                phone=patient_data["phone"],
                email=patient_data["email"],
                date_of_birth=date_of_birth,
                insurance_info=patient_data.get("insurance_info"),
                notes=patient_data.get("notes")
            )
            return patient, None

        except Exception as e:
            return None, f"registration_error: {str(e)}"

    # First try to find existing patient
    lookup_result = patient_repo.find_patient_by_identifiers(
        name=chat_request.patient_name,
        phone=chat_request.patient_phone,
        email=chat_request.patient_email,
        patient_id=chat_request.patient_id
    )

    # 仅当用户至少提供了部分身份信息时才触发“新病人注册”流程
    has_any_identifier = any([
        chat_request.patient_name,
        chat_request.patient_phone,
        chat_request.patient_email,
        chat_request.patient_id
    ])

    # Handle lookup results
    if lookup_result.is_confident_match():
        return lookup_result.patient, None
    elif lookup_result.is_new_patient and has_any_identifier:
        return None, "new_patient_registration"
    elif lookup_result.multiple_matches:
        return None, "multiple_matches"
    else:
        return None, None


def get_patient_context(patient: Patient) -> Optional[Dict]:
    """Get patient context for the conversation."""
    if not patient:
        return None

    # Get upcoming appointments using repository
    upcoming_appts = patient_repo.get_upcoming_appointments(patient)

    context = {
        "patient_id": patient.id,
        "patient_name": patient.name,
        "phone": patient.phone,
        "email": patient.email,
        "date_of_birth": patient.date_of_birth.isoformat(),
        "insurance_info": patient.insurance_info,
        "notes": patient.notes,
        "upcoming_appointments": [
            {
                "id": appt.id,
                "datetime": appt.datetime.isoformat(),
                "type": appt.type.value,
                "status": appt.status.value,
                "duration": appt.duration,
                "dentist": appt.dentist,
                "notes": appt.notes
            }
            for appt in upcoming_appts[:3]  # Limit to next 3 appointments
        ]
    }

    return context


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main chat interface."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat")
async def chat_endpoint(chat_request: ChatRequest):
    """Main chat endpoint for interacting with the scheduling agent."""
    try:
        print(f"[DEBUG] Starting chat endpoint with message: {chat_request.message}")

        # Get or create conversation ID
        conversation_id = chat_request.conversation_id or f"conv_{datetime.now().timestamp()}"
        print(f"[DEBUG] Conversation ID: {conversation_id}")

        # Initialize conversation if new
        if conversation_id not in conversations:
            conversations[conversation_id] = []
            print(f"[DEBUG] Initialized new conversation")

        # Initialize conversation meta if new
        if conversation_id not in conversation_meta:
            conversation_meta[conversation_id] = {}
        meta = conversation_meta[conversation_id]

        # 如果当前对话正在等待用户提供新病人信息，就直接尝试从这条 message 里解析并注册
        if meta.get("mode") == "awaiting_new_patient_info":
            print("[DEBUG] Conversation in registration mode, trying to parse patient info from message...")
            patient_data = parse_patient_info_from_message(chat_request.message)

            # 如果一句话里完全没解析出姓名/电话/邮箱/生日，则认为用户已经偏向正常对话，退出注册模式，继续后续流程
            if not any([
                patient_data.get("name"),
                patient_data.get("phone"),
                patient_data.get("email"),
                patient_data.get("date_of_birth"),
            ]):
                print("[DEBUG] No identifiable patient fields in message, exiting registration mode.")
                meta["mode"] = None
            else:
                try:
                    is_valid, errors = patient_repo.validate_patient_data(patient_data)
                except Exception as e:
                    print(f"[DEBUG] Error in validate_patient_data: {e}")
                    response_text = (
                        "我在检查你提供的信息时遇到了一些问题。\n"
                        "请确认包含：姓名、电话、邮箱、生日(YYYY-MM-DD)，然后再发送一次。"
                    )
                    record_conversation_exchange(conversation_id, chat_request.message, response_text)
                    return ChatResponse(
                        message=response_text,
                        conversation_id=conversation_id,
                        timestamp=datetime.now()
                    )

                if not is_valid:
                    response_text = (
                        "谢谢！我收到了你提供的一部分信息，但有一些问题：\n"
                        + "\n".join(f"- {err}" for err in errors)
                        + "\n\n请重新发送一次，可以按照下面格式：\n"
                          "姓名、电话、邮箱、生日(YYYY-MM-DD)、保险信息（可选）。"
                    )
                    record_conversation_exchange(conversation_id, chat_request.message, response_text)
                    return ChatResponse(
                        message=response_text,
                        conversation_id=conversation_id,
                        timestamp=datetime.now()
                    )

                try:
                    date_of_birth = datetime.fromisoformat(patient_data["date_of_birth"]).date()
                    patient = patient_repo.create_patient(
                        name=patient_data["name"],
                        phone=patient_data["phone"],
                        email=patient_data["email"],
                        date_of_birth=date_of_birth,
                        insurance_info=patient_data.get("insurance_info"),
                        notes=None
                    )
                    # 记录到对话元信息里，并清除注册模式
                    meta["patient_id"] = patient.id
                    meta["mode"] = None

                    response_text = (
                        f"好的，{patient.name}，我已经帮你在系统里注册好了。\n"
                        "接下来你想预约什么样的牙科服务？"
                    )
                    record_conversation_exchange(conversation_id, chat_request.message, response_text)
                    return ChatResponse(
                        message=response_text,
                        conversation_id=conversation_id,
                        timestamp=datetime.now()
                    )
                except Exception as e:
                    print(f"[DEBUG] Error while creating patient from free-text info: {e}")
                    response_text = (
                        "在创建你的病人信息时出了点问题，请稍后再试，或者直接联系诊所前台。"
                    )
                    record_conversation_exchange(conversation_id, chat_request.message, response_text)
                    return ChatResponse(
                        message=response_text,
                        conversation_id=conversation_id,
                        timestamp=datetime.now()
                    )

        # 在进入身份识别前，尝试从当前 message 中自动解析患者身份信息，填充到 chat_request
        # 这样“我叫老王”“我的电话是…”这类一句话自我介绍也能触发新病人识别/匹配逻辑
        if not meta.get("patient_id"):
            parsed_info = parse_patient_info_from_message(chat_request.message)
            # 只有在 chat_request 对应字段为空时才用解析到的信息填充，避免覆盖前端显式传入的值
            if parsed_info.get("name") and not chat_request.patient_name:
                chat_request.patient_name = parsed_info["name"]
            if parsed_info.get("phone") and not chat_request.patient_phone:
                chat_request.patient_phone = parsed_info["phone"]
            if parsed_info.get("email") and not chat_request.patient_email:
                chat_request.patient_email = parsed_info["email"]
            # date_of_birth 先不写入 ChatRequest（模型里可能没有这个字段），在注册模式下再用

            # 如果一次性提供了完整注册信息，直接注册并持久化，避免依赖对话模式/会话保持
            if all([
                parsed_info.get("name"),
                parsed_info.get("phone"),
                parsed_info.get("email"),
                parsed_info.get("date_of_birth"),
            ]):
                try:
                    is_valid, errors = patient_repo.validate_patient_data(parsed_info)
                except Exception as e:
                    print(f"[DEBUG] Error in validate_patient_data: {e}")
                    response_text = (
                        "我在检查你提供的信息时遇到了一些问题。\n"
                        "请确认包含：姓名、电话、邮箱、生日(YYYY-MM-DD)，然后再发送一次。"
                    )
                    record_conversation_exchange(conversation_id, chat_request.message, response_text)
                    return ChatResponse(
                        message=response_text,
                        conversation_id=conversation_id,
                        timestamp=datetime.now()
                    )

                if not is_valid:
                    response_text = (
                        "谢谢！我收到了你提供的一部分信息，但有一些问题：\n"
                        + "\n".join(f"- {err}" for err in errors)
                        + "\n\n请重新发送一次，可以按照下面格式：\n"
                          "姓名、电话、邮箱、生日(YYYY-MM-DD)、保险信息（可选）。"
                    )
                    record_conversation_exchange(conversation_id, chat_request.message, response_text)
                    return ChatResponse(
                        message=response_text,
                        conversation_id=conversation_id,
                        timestamp=datetime.now()
                    )

                lookup_result = patient_repo.find_patient_by_identifiers(
                    name=parsed_info["name"],
                    phone=parsed_info["phone"],
                    email=parsed_info["email"]
                )
                if lookup_result.is_new_patient:
                    try:
                        date_of_birth = datetime.fromisoformat(parsed_info["date_of_birth"]).date()
                        patient = patient_repo.create_patient(
                            name=parsed_info["name"],
                            phone=parsed_info["phone"],
                            email=parsed_info["email"],
                            date_of_birth=date_of_birth,
                            insurance_info=parsed_info.get("insurance_info"),
                            notes=None
                        )
                        meta["patient_id"] = patient.id
                        meta["patient_name"] = patient.name
                        meta["mode"] = None

                        response_text = (
                            f"好的，{patient.name}，我已经帮你在系统里注册好了。\n"
                            "接下来你想预约什么样的牙科服务？"
                        )
                        record_conversation_exchange(conversation_id, chat_request.message, response_text)
                        return ChatResponse(
                            message=response_text,
                            conversation_id=conversation_id,
                            timestamp=datetime.now()
                        )
                    except Exception as e:
                        print(f"[DEBUG] Error while creating patient from parsed info: {e}")
                        response_text = (
                            "在创建你的病人信息时出了点问题，请稍后再试，或者直接联系诊所前台。"
                        )
                        record_conversation_exchange(conversation_id, chat_request.message, response_text)
                        return ChatResponse(
                            message=response_text,
                            conversation_id=conversation_id,
                            timestamp=datetime.now()
                        )

        # Identify patient and check for special handling
        print(f"[DEBUG] Calling get_or_identify_patient...")
        patient, special_action = get_or_identify_patient(chat_request)

        print(f"[DEBUG] Patient: {patient}, Special action: {special_action}")

        # Handle special cases
        if special_action:
            if special_action == "new_patient_registration":
                # 标记当前对话正在等待新病人信息
                conversation_meta[conversation_id]["mode"] = "awaiting_new_patient_info"

                response_text = (
                    "Welcome! I don't see your information in our system. "
                    "To get you set up as a new patient, I'll need some information from you. "
                    "Could you please provide:\n"
                    "1. Your full name\n"
                    "2. Your phone number\n"
                    "3. Your email address\n"
                    "4. Your date of birth (YYYY-MM-DD)\n"
                    "5. Your insurance information (if applicable)"
                )
                record_conversation_exchange(conversation_id, chat_request.message, response_text)
                return ChatResponse(
                    message=response_text,
                    conversation_id=conversation_id,
                    timestamp=datetime.now()
                )

            elif special_action == "multiple_matches":
                # Get the lookup result to see which patients matched
                lookup_result = patient_repo.find_patient_by_identifiers(
                    name=chat_request.patient_name,
                    phone=chat_request.patient_phone,
                    email=chat_request.patient_email,
                    patient_id=chat_request.patient_id
                )

                if lookup_result.multiple_matches:
                    patient_list = "\n".join([
                        f"- {p.name} (Phone: {p.phone}, Email: {p.email})"
                        for p in lookup_result.multiple_matches[:3]
                    ])
                    response_text = (
                        f"I found multiple patients with similar information. Could you help me identify you?\n"
                        f"{patient_list}\n\n"
                        "Could you please provide your patient ID or additional information to help me find the correct record?"
                    )
                    record_conversation_exchange(conversation_id, chat_request.message, response_text)
                    return ChatResponse(
                        message=response_text,
                        conversation_id=conversation_id,
                        timestamp=datetime.now()
                    )

            elif special_action.startswith("validation_error"):
                error_msg = special_action.replace("validation_error: ", "")
                response_text = f"There are some issues with the information provided: {error_msg}. Please correct these and try again."
                record_conversation_exchange(conversation_id, chat_request.message, response_text)
                return ChatResponse(
                    message=response_text,
                    conversation_id=conversation_id,
                    timestamp=datetime.now()
                )

            elif special_action.startswith("registration_error"):
                error_msg = special_action.replace("registration_error: ", "")
                response_text = f"I encountered an error while creating your patient record: {error_msg}. Please try again or contact the clinic."
                record_conversation_exchange(conversation_id, chat_request.message, response_text)
                return ChatResponse(
                    message=response_text,
                    conversation_id=conversation_id,
                    timestamp=datetime.now()
                )

        # Persist identified patient context for later queries
        if patient:
            conversation_meta[conversation_id]["patient_id"] = patient.id
            conversation_meta[conversation_id]["patient_name"] = patient.name

        # Get patient context if we have a patient
        patient_context = get_patient_context(patient) if patient else None

        # Add user message to conversation history
        user_message = {
            "role": "user",
            "content": chat_request.message,
            "timestamp": datetime.now().isoformat()
        }
        conversations[conversation_id].append(user_message)

        # Get AI response
        print(f"[DEBUG] About to call LLM for scheduling...")
        ai_response_text, schedule_update_data = call_llm_for_scheduling(
            chat_request.message,
            conversations[conversation_id],
            patient_context
        )
        print(f"[DEBUG] LLM response received. Response length: {len(ai_response_text)}, Schedule update: {schedule_update_data}")

        # Add AI response to conversation history
        ai_message = {
            "role": "assistant",
            "content": ai_response_text,
            "timestamp": datetime.now().isoformat()
        }
        conversations[conversation_id].append(ai_message)

        # Process any schedule updates
        schedule_update = None
        print(f"[DEBUG] Processing schedule updates...")
        if schedule_update_data:
            print(f"[DEBUG] Schedule update data found: {schedule_update_data}")
            # Convert status string to enum
            if "status" in schedule_update_data:
                try:
                    print(f"[DEBUG] Converting status to enum...")
                    status_enum = AppointmentStatus(schedule_update_data["status"])
                    schedule_update_data["status"] = status_enum
                    print(f"[DEBUG] Status enum created: {status_enum}")

                    # Convert datetime strings if present
                    if schedule_update_data.get("original_appointment"):
                        print(f"[DEBUG] Converting original appointment datetime...")
                        schedule_update_data["original_appointment"] = datetime.fromisoformat(
                            schedule_update_data["original_appointment"]
                        )
                    if schedule_update_data.get("new_appointment"):
                        print(f"[DEBUG] Converting new appointment datetime...")
                        schedule_update_data["new_appointment"] = datetime.fromisoformat(
                            schedule_update_data["new_appointment"]
                        )

                    print(f"[DEBUG] Creating ScheduleUpdate object...")
                    schedule_update = ScheduleUpdate(**schedule_update_data)
                    print(f"[DEBUG] ScheduleUpdate created: {schedule_update}")
                except ValueError as e:
                    print(f"Error parsing schedule update: {e}")
        else:
            print(f"[DEBUG] No schedule update data to process")

        # Persist any schedule updates for consistency
        if schedule_update:
            try:
                persist_appointment_from_schedule_update(patient, schedule_update)
            except Exception as e:
                print(f"[DEBUG] Error persisting appointment from schedule_update in chat_endpoint: {e}")

        save_conversations_to_file()

        response = ChatResponse(
            message=ai_response_text,
            schedule_update=schedule_update,
            conversation_id=conversation_id,
            timestamp=datetime.now()
        )

        return response

    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/appointments")
async def get_appointments(
    patient_id: Optional[str] = None,
    patient_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
):
    """Get appointments with optional filters."""
    try:
        def _parse_date(value: Optional[str], default_time: time) -> Optional[datetime]:
            if not value:
                return None
            if len(value) == 10:
                return datetime.combine(datetime.fromisoformat(value).date(), default_time)
            return datetime.fromisoformat(value)

        start_dt = _parse_date(date_from, time.min)
        end_dt = _parse_date(date_to, time.max)

        appointments = patient_repo.get_all_appointments()

        if patient_id:
            appointments = [appt for appt in appointments if appt.patient_id == patient_id]
        if patient_name:
            appointments = [appt for appt in appointments if appt.patient_name == patient_name]
        if status:
            appointments = [appt for appt in appointments if appt.status.value == status]
        if start_dt:
            appointments = [appt for appt in appointments if appt.datetime >= start_dt]
        if end_dt:
            appointments = [appt for appt in appointments if appt.datetime <= end_dt]
        if keyword:
            keyword_lower = keyword.lower()
            appointments = [
                appt for appt in appointments
                if keyword_lower in (appt.notes or "").lower()
                or keyword_lower in appt.patient_name.lower()
                or keyword_lower in (appt.dentist or "").lower()
            ]

        return {
            "appointments": [
                {
                    "id": appt.id,
                    "patient_name": appt.patient_name,
                    "patient_id": appt.patient_id,
                    "datetime": appt.datetime.isoformat(),
                    "type": appt.type.value,
                    "status": appt.status.value,
                    "duration": appt.duration,
                    "dentist": appt.dentist,
                    "notes": appt.notes
                }
                for appt in appointments
            ]
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD or ISO datetime.")
    except Exception as e:
        print(f"Error getting appointments: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve appointments")


@app.post("/appointments")
async def create_appointment(appointment_data: AppointmentCreateRequest):
    """Create a new appointment for an existing patient."""
    try:
        patient = None
        if appointment_data.patient_id:
            patient = scheduler.find_patient_by_id(appointment_data.patient_id)
        if not patient and appointment_data.patient_name:
            patient = scheduler.find_patient_by_name(appointment_data.patient_name)

        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        appointment_dt = datetime.fromisoformat(appointment_data.datetime)

        duration = appointment_data.duration
        if not duration and scheduler.availability:
            appt_info = scheduler.availability.appointment_types.get(appointment_data.type)
            if appt_info:
                duration = appt_info.duration
        if not duration:
            duration = 60

        existing = patient_repo.get_all_appointments()
        max_id_num = 0
        for appt in existing:
            appt_id = appt.id
            if isinstance(appt_id, str) and appt_id.startswith("A"):
                try:
                    max_id_num = max(max_id_num, int(appt_id[1:]))
                except ValueError:
                    continue
        new_id = f"A{max_id_num + 1:03d}"

        appointment = Appointment(
            id=new_id,
            patient_id=patient.id,
            patient_name=patient.name,
            datetime=appointment_dt,
            duration=duration,
            type=appointment_data.type,
            status=AppointmentStatus.SCHEDULED,
            notes=appointment_data.notes,
            dentist=appointment_data.dentist,
        )

        patient_repo.add_or_update_appointment(appointment)
        scheduler.reload_appointments()

        return {
            "message": "Appointment created successfully",
            "appointment": {
                "id": appointment.id,
                "patient_id": appointment.patient_id,
                "patient_name": appointment.patient_name,
                "datetime": appointment.datetime.isoformat(),
                "type": appointment.type.value,
                "status": appointment.status.value,
                "duration": appointment.duration,
                "dentist": appointment.dentist,
                "notes": appointment.notes,
            },
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO datetime.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating appointment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create appointment")


@app.get("/patients")
async def get_patients(
    patient_id: Optional[str] = None,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
):
    """Get all patients, with optional filters."""
    try:
        patients = patient_repo.get_all_patients()
        if patient_id:
            patients = [p for p in patients if p.id == patient_id]
        if name:
            patients = [p for p in patients if p.name == name]
        if phone:
            patients = [p for p in patients if p.phone == phone]
        if email:
            patients = [p for p in patients if p.email == email]

        return {
            "patients": [
                {
                    "id": patient.id,
                    "name": patient.name,
                    "phone": patient.phone,
                    "email": patient.email,
                    "insurance_info": patient.insurance_info,
                    "notes": patient.notes
                }
                for patient in patients
            ]
        }
    except Exception as e:
        print(f"Error getting patients: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve patients")


@app.get("/availability")
async def get_availability(date_str: str):
    """Get available time slots for a specific date."""
    try:
        target_date = datetime.fromisoformat(date_str).date()

        # Get available slots for different appointment types
        availability = {}
        for appt_type in [AppointmentType.REGULAR_CHECKUP, AppointmentType.INITIAL_CONSULTATION]:
            slots = scheduler.find_available_slots(target_date, appt_type)
            availability[appt_type.value] = [
                {
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat(),
                    "available": slot.available,
                    "dentist": slot.dentist
                }
                for slot in slots
            ]

        return {
            "date": date_str,
            "availability": availability
        }

    except Exception as e:
        print(f"Error getting availability: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve availability")


@app.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history."""
    try:
        if conversation_id not in conversations:
            file_conversations, file_meta = load_conversations_from_file()
            conversations.update(file_conversations)
            conversation_meta.update(file_meta)
        if conversation_id not in conversations:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {
            "conversation_id": conversation_id,
            "messages": conversations[conversation_id]
        }
    except Exception as e:
        print(f"Error getting conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation")


@app.get("/conversations")
async def list_conversations(
    patient_id: Optional[str] = None,
    patient_name: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """List conversations with optional filters."""
    try:
        def _parse_date(value: Optional[str], default_time: time) -> Optional[datetime]:
            if not value:
                return None
            if len(value) == 10:
                return datetime.combine(datetime.fromisoformat(value).date(), default_time)
            return datetime.fromisoformat(value)

        start_dt = _parse_date(date_from, time.min)
        end_dt = _parse_date(date_to, time.max)

        file_conversations, file_meta = load_conversations_from_file()
        results = []
        for conv_id, messages in file_conversations.items():
            meta = file_meta.get(conv_id, {})
            if patient_id and meta.get("patient_id") != patient_id:
                continue
            if patient_name and meta.get("patient_name") != patient_name:
                continue
            if keyword:
                keyword_lower = keyword.lower()
                if not any(keyword_lower in (msg.get("content") or "").lower() for msg in messages):
                    continue
            if start_dt or end_dt:
                timestamps = [
                    datetime.fromisoformat(msg["timestamp"])
                    for msg in messages
                    if msg.get("timestamp")
                ]
                if timestamps:
                    min_ts = min(timestamps)
                    max_ts = max(timestamps)
                    if start_dt and max_ts < start_dt:
                        continue
                    if end_dt and min_ts > end_dt:
                        continue

            results.append({
                "conversation_id": conv_id,
                "patient_id": meta.get("patient_id"),
                "patient_name": meta.get("patient_name"),
                "message_count": len(messages),
                "last_message_at": messages[-1]["timestamp"] if messages else None,
            })

        return {"conversations": results}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD or ISO datetime.")
    except Exception as e:
        print(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to list conversations")



@app.post("/appointment/{appointment_id}/confirm")
async def confirm_appointment(appointment_id: str):
    """Confirm an appointment."""
    try:
        success = scheduler.confirm_appointment(appointment_id)
        if success:
            # 这里只更新 scheduler 内存状态；appointments.json 的写入在创建预约时完成
            return {"message": "Appointment confirmed successfully"}
        else:
            raise HTTPException(status_code=404, detail="Appointment not found")
    except Exception as e:
        print(f"Error confirming appointment: {e}")
        raise HTTPException(status_code=500, detail="Failed to confirm appointment")



@app.post("/appointment/{appointment_id}/cancel")
async def cancel_appointment(appointment_id: str):
    """Cancel an appointment."""
    try:
        success = scheduler.cancel_appointment(appointment_id)
        if success:
            # 同上，这里只更新 scheduler 内存状态
            return {"message": "Appointment cancelled successfully"}
        else:
            raise HTTPException(status_code=404, detail="Appointment not found")
    except Exception as e:
        print(f"Error cancelling appointment: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel appointment")


@app.post("/register-patient")
async def register_patient(patient_data: PatientRegistrationRequest):
    """Register a new patient."""
    try:
        # Validate patient data
        data_dict = patient_data.dict()
        is_valid, errors = patient_repo.validate_patient_data(data_dict)

        if not is_valid:
            raise HTTPException(status_code=400, detail={"errors": errors})

        # Check if patient already exists
        existing_result = patient_repo.find_patient_by_identifiers(
            name=patient_data.name,
            phone=patient_data.phone,
            email=patient_data.email
        )

        if existing_result.is_confident_match():
            raise HTTPException(
                status_code=409,
                detail="A patient with this information already exists in our system"
            )

        # Create new patient
        date_of_birth = datetime.fromisoformat(patient_data.date_of_birth).date()
        patient = patient_repo.create_patient(
            name=patient_data.name,
            phone=patient_data.phone,
            email=patient_data.email,
            date_of_birth=date_of_birth,
            insurance_info=patient_data.insurance_info,
            notes=patient_data.notes
        )

        return {
            "message": "Patient registered successfully",
            "patient": {
                "id": patient.id,
                "name": patient.name,
                "phone": patient.phone,
                "email": patient.email
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error registering patient: {e}")
        raise HTTPException(status_code=500, detail="Failed to register patient")


@app.post("/find-patient")
async def find_patient(name: Optional[str] = None, phone: Optional[str] = None,
                      email: Optional[str] = None):
    """Find patient by various identifiers."""
    try:
        lookup_result = patient_repo.find_patient_by_identifiers(
            name=name, phone=phone, email=email
        )

        if lookup_result.is_confident_match():
            return {
                "found": True,
                "patient": {
                    "id": lookup_result.patient.id,
                    "name": lookup_result.patient.name,
                    "phone": lookup_result.patient.phone,
                    "email": lookup_result.patient.email
                }
            }
        elif lookup_result.multiple_matches:
            return {
                "found": False,
                "multiple_matches": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "phone": p.phone,
                        "email": p.email
                    }
                    for p in lookup_result.multiple_matches
                ],
                "message": "Multiple patients found. Please provide more specific information."
            }
        else:
            return {
                "found": False,
                "message": "No patient found with the provided information. Would you like to register as a new patient?"
            }

    except Exception as e:
        print(f"Error finding patient: {e}")
        raise HTTPException(status_code=500, detail="Failed to find patient")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "llm_configured": llm_client is not None,
        "llm_model": llm_model,
        "llm_base_url": os.getenv("LLM_BASE_URL")
    }


if __name__ == "__main__":
    print("Starting DentFlow Scheduling Server...")
    print("Available at: http://127.0.0.1:8000")

    # Create static directory if it doesn't exist
    Path("app/ui/static").mkdir(exist_ok=True)

    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
