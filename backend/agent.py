import json
import os
from typing import Dict, List, Any

import httpx

from backend import tools

SYSTEM_PROMPT = """
你是牙医预约助手。遵循以下规则：
1) 必须先获取病人 name 和 dob(YYYY-MM-DD)，再判断是否新病人。
2) 调用 is_new_patient。
3) 新病人必须询问并解析 name, dob, email, phone，然后调用 registration_new_patient。
4) 预约流程：询问预约时间，解析 year/month/day/start_time/end_time，先调用 is_conflict_appointment。
5) 无冲突才调用 make_appointment；有冲突则要求更换时间。
6) 查询流程：输入 name + dob，调用 get_patient_info_and_appointments，返回 patient_id 和预约信息（或“暂无预约”）。
7) 所有工具调用必须使用 function calling。
""".strip()


def _tool_spec() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "is_new_patient",
                "description": "Check if the patient is new by name and dob.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "dob": {"type": "string"},
                    },
                    "required": ["name", "dob"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "registration_new_patient",
                "description": "Register a new patient and return patient info.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "dob": {"type": "string"},
                        "email": {"type": "string"},
                        "phone": {"type": "string"},
                    },
                    "required": ["name", "dob", "email", "phone"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "is_conflict_appointment",
                "description": "Check if a time slot conflicts with existing appointments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "year": {"type": "integer"},
                        "month": {"type": "integer"},
                        "day": {"type": "integer"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                    },
                    "required": ["year", "month", "day", "start_time", "end_time"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "make_appointment",
                "description": "Create an appointment for a patient.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "dob": {"type": "string"},
                        "year": {"type": "integer"},
                        "month": {"type": "integer"},
                        "day": {"type": "integer"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                    },
                    "required": ["name", "dob", "year", "month", "day", "start_time", "end_time"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_patient_info_and_appointments",
                "description": "Get patient info and their appointments by name and dob.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "dob": {"type": "string"},
                    },
                    "required": ["name", "dob"],
                },
            },
        },
    ]


def _call_tool(name: str, arguments: Dict[str, Any]) -> Any:
    if name == "is_new_patient":
        return tools.is_new_patient(**arguments)
    if name == "registration_new_patient":
        return tools.registration_new_patient(**arguments)
    if name == "is_conflict_appointment":
        return tools.is_conflict_appointment(**arguments)
    if name == "make_appointment":
        return tools.make_appointment(**arguments)
    if name == "get_patient_info_and_appointments":
        return tools.get_patient_info_and_appointments(**arguments)
    raise ValueError(f"Unknown tool: {name}")


class ChatAgent:
    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")
        self.timeout = float(os.getenv("LLM_TIMEOUT", "60"))

        if not self.base_url:
            raise RuntimeError("LLM_BASE_URL is required")

    def _request(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": _tool_spec(),
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    def chat(self, conversation: List[Dict[str, Any]]) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation

        for _ in range(6):
            response = self._request(messages)
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls") or []

            if tool_calls:
                messages.append(message)
                for call in tool_calls:
                    call_id = call.get("id")
                    func = call.get("function", {})
                    name = func.get("name")
                    args_str = func.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}
                    result = _call_tool(name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(result, ensure_ascii=True),
                        }
                    )
                continue

            content = message.get("content")
            if content:
                return content

        return "抱歉，当前请求处理失败，请稍后再试。"
