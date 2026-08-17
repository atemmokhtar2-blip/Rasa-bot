# Production Runbook

## Required Services

التشغيل الإنتاجي يحتاج PostgreSQL وRedis وبيانات أسرار فعلية. لا يستخدم Docker Compose أي خدمة وهمية؛ ملف `docker-compose.yml` يشغّل صور PostgreSQL وRedis الرسمية، بينما يحتاج Telegram token وRasa endpoint إلى إعداد من المشغّل.

## Configuration

انسخ `.env.example` إلى `.env` وعدّل `DATABASE_URL` و`REDIS_URL` و`API_KEY_PEPPER` و`TELEGRAM_BOT_TOKEN` و`TELEGRAM_WEBHOOK_SECRET`. لا تضع الأسرار في Git.

## Start

```bash
docker compose up --build
```

الخدمة API تستمع على المنفذ 8000، والـ Worker يقرأ من Redis queue. إذا لم يكن Docker مثبتًا على الجهاز، يجب تثبيته أولًا؛ لا يوجد بديل وهمي داخل الكود.

## Database

عند بدء الحاوية، تستدعي ApplicationContainer `create_schema()` لإنشاء الجداول المعرّفة في SQLAlchemy. ملف `migrations/001_initial.sql` موجود للمراجعة والترحيل المنضبط، ويمكن تشغيله عبر أداة migrations في بيئة الإدارة.

## Real Integrations

`RasaTrainer` يستدعي executable `rasa` الحقيقي. إذا لم يكن Rasa مثبتًا أو endpoint غير متاح، يفشل التشغيل برسالة واضحة ولا يرجع نتيجة تدريب مصطنعة. `RedisRateLimiter` و`RedisQueue` يستخدمان Redis الحقيقي عند ضبط `REDIS_URL`. `SQLDatabase` يستخدم PostgreSQL عبر `asyncpg` عند ضبط `DATABASE_URL`.

## Health

`/health` يفحص سلامة التطبيق الأساسية، بينما `/ready` يفحص PostgreSQL وRedis فعليًا عندما يكونان مفعّلين ويعيد `not_ready` إذا تعذر الاتصال.
