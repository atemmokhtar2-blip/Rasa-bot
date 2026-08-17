# Specification 06: Training and Model Lifecycle SDK

يوفر الإصدار السادس بنية **project-isolated** لإدارة إصدارات البيانات، التدريب، تقييم النماذج، بوابات الجودة، والنشر القابل للتراجع. كل Dataset Version وModel Version غير قابل للتعديل بعد إنشائه؛ أي تعديل ينتج إصدارًا جديدًا مع lineage وchecksum مستقلين.

## Dataset lifecycle

يمكن إنشاء Dataset Version عبر `POST /api/v1/datasets` ثم إضافة إصدارات عبر `POST /api/v1/datasets/{dataset_id}/versions`. تحفظ pipeline الإحصاءات، class imbalance، leakage، quality score، checksum، ومعلومات lineage. يدعم التشغيل المحلي `DatasetRegistry` عندما لا يتوفر PostgreSQL، بينما تستخدم بيئة الإنتاج repositories SQL مع نفس contract.

```bash
curl -X POST http://localhost:8000/api/v1/datasets \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: <project-key>' \
  -d '{"project_id":"p1","name":"support","version":"1.0.0","language":"ar","examples":[{"text":"مرحبا","intent":"greet"}]}'
```

تستخدم الاستيرادات JSON وJSONL وCSV، ويجب أن يظل الإصدار الناتج immutable. يفضل JSONL للبيانات الكبيرة لأنه قابل للمعالجة المتدفقة، وتبقى حدود المشروع مطبقة قبل إنشاء الإصدار أو قراءته.

## Training lifecycle

يُنشأ التدريب من خلال `POST /api/v1/training/jobs` أو alias `POST /api/v1/training`. الطلب يحمل `project_id` و`dataset_version` و`provider` و`training_config`. في الوضع المحلي تُخزن المهمة في `training_jobs_memory` وتوضع في `TrainingQueue`، أما الإنتاج فيستخدم SQL وRedis. يدعم المساران نفس idempotency key ونفس بنية الحالة.

الحالات الأساسية هي `queued`, `running`, `completed`, `failed`, `cancel_requested`, و`cancelled`. يسجل العامل `worker_id`, heartbeat، stage، progress، retry count، وerror structured. لا يجوز للعامل اعتماد Dataset غير تابع للمشروع أو إنشاء Model Version من Dataset غير immutable.

```bash
curl -X POST http://localhost:8000/api/v1/training/jobs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: train-p1-001' \
  -H 'X-API-Key: <project-key>' \
  -d '{"project_id":"p1","dataset_version":"support:1.0.0","provider":"rasa","training_config":{"epochs":10}}'
```

## Evaluation and quality gates

تُخزن metrics وevaluation report مع Model Version. يستخدم `ConfigurableQualityGate` thresholds صريحة، ويعيد قرارًا structured يحتوي `passed`, `failures`, و`metrics`. إذا فشلت البوابة، لا يسمح مسار النشر بترقية النموذج إلى alias إنتاجي.

`RegressionDetector` يقارن metrics الإصدار الجديد بخط أساس production ويصدر فروقًا قابلة للتدقيق. يجب اعتبار انخفاض metric أعلى من tolerance regression، مع عدم اعتبار metric المفقود نجاحًا صامتًا.

## Model registry and deployment

Model Version يحمل `model_id`, `version`, `project_id`, `dataset_id`, `dataset_version`, `training_job_id`, `artifact_uri`, و`artifact_checksum`. لا يعتمد `ModelRouter` على أسماء hardcoded؛ بل يحل alias من `(project_id, environment, alias)`، مثل `production`, `staging`, أو alias مخصص.

يفحص `DeploymentManager` وجود artifact قبل الترقية ويسجل deployment history. عند rollback يعيد alias السابق فقط إذا كان artifact السابق ما زال موجودًا، وإلا يرفض العملية بدل إنشاء route غير صالح.

```python
router.set_alias("p1", "production", "production", "model-support", "2.1.0")
active = router.resolve("p1", "production", "production")
# ("model-support", "2.1.0")
```

## Recovery and operations

يعتمد `TrainingRecoveryService` على انتهاء heartbeat لا على مدة ثابتة للمهمة. يعيد orphaned jobs إلى `queued` ضمن حد retries، أو يضعها `failed` بعد استنفاد الحد، ويسجل السبب والـ timestamps. يجب تشغيل recovery دوريًا في بيئة الإنتاج، بينما يمكن استدعاؤه مباشرة في اختبارات Local-first.

جميع الاستدعاءات الحساسة تسجل `request_id`, `project_id`, `job_id`, `dataset_version`, `model_version`, والنتيجة. الأخطاء تستخدم Framework error envelope ولا تكشف secrets أو تفاصيل الاتصال الداخلية.

## Validation commands

```bash
python3 -m compileall -q framework tests
pytest -q
```

يجب أن تنجح اختبارات Spec 06 الخاصة بالإحصاءات وتسرب البيانات، deterministic split، checksum artifacts، queue idempotency، quality gates، router resolution، deployment، والrollback.

> **Definition of Done:** Dataset Version immutable ومتحقق، Training Job project-isolated وله heartbeat/recovery، Evaluation وRegression Detection مرتبطان بالإصدار، Quality Gate يمنع الترقية غير الصالحة، Deployment قابل للـ rollback، وModel Router يحل aliases حسب المشروع والبيئة دون hardcoded models.
