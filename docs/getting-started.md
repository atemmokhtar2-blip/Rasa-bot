# Getting Started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env
pytest -q
uvicorn framework.api.app:app --reload
```

بعد التشغيل:

- `GET /health`
- `GET /ready`
- `POST /api/v1/messages` مع `{ "project_id": "demo", "user_id": "u1", "text": "/start" }`

لا تضع أسرار Telegram أو Rasa في المصدر. استخدم ملفات البيئة أو Secret Provider مستقبلاً.
