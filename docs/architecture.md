# Architecture

الإصدار الأول يبني **AI Developer Framework** وليس بوتًا أحادي الملف. يعتمد `framework.core` على نماذج داخلية وواجهات مجردة، بينما ينفذ `TelegramAdapter` عملية التطبيع والإرسال فقط. محرك `RasaProvider` موجود كمزوّد NLU قابل للاستبدال، ويوجد مزوّد قواعد محلي للاختبارات والتطوير دون خدمة خارجية.

## Pipeline

`IncomingMessage → NLUProvider → Intent/Entities → ActionRegistry → OutgoingResponse`

## Boundaries

| المكوّن | المسؤولية | ما لا يفعله |
|---|---|---|
| Core Engine | إدارة Pipeline والأحداث والـ fallback | لا يستورد Telegram أو Rasa مباشرة |
| Channel Adapter | تحويل payload خارجي إلى رسالة داخلية وإرسال response | لا يحتوي Business Logic |
| NLU Provider | اكتشاف intent واستخراج entities | لا يرسل ردودًا للقنوات |
| Action | تنفيذ Workflow مستقل عن القناة | لا يعرف Telegram API |
| Event Bus | نشر أحداث Structured | لا يفرض تخزينًا بعينه |
| Repository | عزل الوصول للبيانات | لا يقرر سياسة الحوار |

## قرارات الإصدار الأول

تم اختيار Python مع FastAPI وPydantic كأساس API typed وقابل للتوسع، مع Repository abstraction ومخزن ذاكرة للاختبارات والبداية. يمكن إضافة PostgreSQL وRedis دون تغيير الـ Core عبر تنفيذ مزوّدين جديدين.
