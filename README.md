# Rasa-bot

**AI Developer Framework**: منصة مطورين Telegram-first، مع Core مستقل عن Telegram وRasa.

## الحالة الحالية

تم تنفيذ Foundation V1 القابلة للاختبار. راجع [خطة التنفيذ](docs/implementation-plan.md) و[الشرح المعماري](docs/architecture.md).

## تشغيل سريع

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest -q
uvicorn framework.api.app:app --reload
```
