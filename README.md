# 牙医预约 Agent Web

前后端分离：`backend/`（FastAPI） + `frontend/`（原生 HTML/JS）。

## 1. 环境准备

- Python 版本：3.10+
- 在项目根目录创建 `.env`（示例，不含真实 key）：

```env
LLM_PROVIDER=openai
LLM_MODEL=deepseek-v3.2-exp
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://aiapi.iiis.co:9443/v1
LLM_TIMEOUT=60

APP_HOST=0.0.0.0
APP_PORT=8000
```

## 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## 3. 启动前端

```bash
cd frontend
python -m http.server 5173
```

浏览器访问：`http://localhost:5173`

## 4. data 目录说明

- `data/patients.json`：病人信息列表（JSON 数组）
- `data/appointments.json`：预约信息列表（JSON 数组）
- 文件不存在会自动创建，初始为 `[]`

## 5. 示例对话

1) 新病人注册
```
用户：你好
助手：请先提供您的姓名和生日（YYYY-MM-DD）。
用户：张三，1990-02-15
助手：请提供邮箱和手机号。
用户：zhangsan@example.com，13800000000
助手：已完成注册，欢迎您张三！
```

2) 成功预约
```
用户：我想预约洗牙
助手：请提供预约日期和时间段（例如 2025-01-20 09:00-09:30）。
用户：2025-01-20 09:00-09:30
助手：预约成功，已为您安排 2025-01-20 09:00-09:30。
```

3) 查询 patient_id 和预约
```
用户：我要查询我的预约
助手：请提供姓名和生日（YYYY-MM-DD）。
用户：张三，1990-02-15
助手：您的 patient_id：AB12CD34EF，预约：2025-01-20 09:00-09:30。
```
