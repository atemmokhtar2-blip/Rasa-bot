from __future__ import annotations
import os
import time
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
RASA_URL = os.environ.get("RASA_ENDPOINT", "http://127.0.0.1:5005").rstrip("/")
API = f"https://api.telegram.org/bot{TOKEN}"

def telegram(method: str, payload: dict | None = None) -> dict:
    response = requests.post(f"{API}/{method}", json=payload or {}, timeout=35)
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"): raise RuntimeError(f"Telegram {method} failed")
    return body["result"]

def parse(text: str, chat_id: str) -> dict:
    response = requests.post(f"{RASA_URL}/model/parse", json={"text": text, "metadata": {"telegram_chat_id": chat_id}}, timeout=30)
    response.raise_for_status()
    return response.json()

def response_text(intent: str, confidence: float, text: str) -> str:
    if confidence < 0.35 or intent == "nlu_fallback": return "لم أفهم طلبك بالكامل. من فضلك أعد صياغته."
    if intent == "greet": return "أهلًا بك، كيف يمكنني مساعدتك؟"
    if intent == "goodbye": return "إلى اللقاء."
    if intent == "get_order_status": return "تم استلام طلب معرفة حالة الطلب. أرسل رقم الطلب إذا لم يكن موجودًا."
    if intent == "cancel_order": return "تم استلام طلب إلغاء الطلب. هل تؤكد الإلغاء؟"
    if intent == "book": return "تم استلام طلب الحجز. ما الموعد الذي تريده؟"
    return f"فهمت طلبك: {text}"

def main() -> None:
    offset = None
    me = telegram("getMe")
    print(f"Telegram polling started for @{me.get('username')}; Rasa={RASA_URL}", flush=True)
    while True:
        updates = telegram("getUpdates", {"timeout": 25, **({"offset": offset} if offset is not None else {})})
        for update in updates:
            offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            text = message.get("text")
            chat = message.get("chat") or {}
            if not text or not chat.get("id"): continue
            try:
                parsed = parse(text, str(chat["id"]))
                intent = (parsed.get("intent") or {}).get("name", "fallback")
                confidence = float((parsed.get("intent") or {}).get("confidence", 0.0))
                telegram("sendMessage", {"chat_id": chat["id"], "text": response_text(intent, confidence, text)})
                print(f"processed update={update['update_id']} intent={intent} confidence={confidence:.3f}", flush=True)
            except Exception as exc:
                print(f"update={update['update_id']} failed: {type(exc).__name__}", flush=True)
                try: telegram("sendMessage", {"chat_id": chat["id"], "text": "حدث خطأ مؤقت أثناء معالجة الرسالة."})
                except Exception: pass
        time.sleep(0.2)

if __name__ == "__main__": main()
