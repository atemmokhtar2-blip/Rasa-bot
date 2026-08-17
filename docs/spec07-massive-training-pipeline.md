# Implementation Specification 07

## Massive Training & Dataset Intelligence Pipeline

هذا المستند يصف التنفيذ الفعلي لدورة التدريب واسعة النطاق داخل Framework. التصميم يفصل Core Engine عن مصادر البيانات، ويجعل كل Dataset Version وModel Version قابلًا للتتبع وغير قابل للتعديل بعد النشر.

> Raw Data → Ingestion → Validation → Cleaning → Normalization → Deduplication → Intent/Entity/Context Processing → Dataset Versioning → Split → Training → Evaluation → Error Analysis → Dataset Improvement → Retraining → Model Versioning → Registry → Deployment Candidate → Production Model

## طبقة البيانات

يقدم `framework.datasets.ingestion` عقود `DataSource` و`DataLoader` وطبقة `StructuredDataLoader` لمعالجة JSON وJSONL وCSV وYAML. يدعم JSONL القراءة سجلًا بعد سجل، كما تعرض `StreamingDatasetImporter.iter_data` أمثلة قابلة للاستهلاك التدريجي بدل فرض تحميل المصدر كاملًا على Core Engine.

يتم تحويل كل سجل إلى `TrainingExample` داخلي موحد، بحيث لا تعتمد الطبقات الداخلية مباشرة على Rasa format. يحتوي السجل على النص، intent، entities، language، metadata، source، conversation_id، review status، وحقول التتبع اللازمة للـ lineage.

## التنظيف والتطبيع

تستخدم `ArabicNormalizer` تطبيع Unicode محافظًا، وتسمح بشكل مستقل بتوحيد صيغ الألف، إزالة التطويل، إزالة التشكيل، ضغط المسافات، وتطبيع علامات الترقيم. الإعداد الافتراضي لا يزيل التشكيل ولا يفرض حذف المعلومات اللغوية.

تقوم `MassiveDatasetCleaner` باكتشاف العينات الفارغة، النصوص غير الصالحة، intents غير المعروفة، entity types غير المعروفة، offsets غير الصحيحة، exact duplicates، وnear duplicates. لا تحذف near duplicates تلقائيًا؛ بل تحفظها مع similarity report لأن التنوع اللغوي قد يكون مفيدًا للنموذج.

| الفحص | النتيجة المسجلة |
|---|---|
| Empty sample | `EMPTY_SAMPLE` وعداد العينات المحذوفة |
| Invalid intent | `UNKNOWN_INTENT` |
| Invalid entity | `INVALID_ENTITY` مع عداد مستقل |
| Exact duplicate | يحذف التكرار المتطابق فقط |
| Near duplicate | similarity pair للمراجعة البشرية |
| Quality | score محسوب من حجم العيوب والتكرار |

## المحادثات والسياق

تجمع `records_to_conversations` السجلات ذات `conversation_id` في `ConversationExample` مستقل، وتحافظ على ترتيب turns، role، intent، entities، expected action، expected state، وcontext metadata مثل `previous_intent` و`turn_number`. ويظل تقسيم Dataset في `DatasetPipeline.split` conversation-aware، فلا يتم توزيع turns من Conversation واحدة على train وtest معًا.

## Dataset Versioning وLineage

تستخدم `DatasetRegistry` مفتاح `(dataset_id, version)` لمنع إعادة استخدام الإصدار المنشور. يتضمن checksum محتوى الأمثلة والمحادثات، كما يحتفظ الإصدار بـ `created_by` وmetadata وstatistics. أي تغيير يجب أن ينتج نسخة جديدة بدل تعديل نسخة منشورة.

## Reproducibility

ينشئ `ReproducibilityManifest` لكل تدريب ناجح أو فاشل. يحفظ manifest العناصر التالية:

| المجال | البيانات |
|---|---|
| Dataset | version وchecksum |
| Training | configuration وhyperparameters وrandom seed |
| Model | model version |
| Runtime | framework version وprovider/Rasa version وPython/platform |
| Language | اللغة المستخدمة في التدريب |
| Time | training timestamp |
| Evaluation | evaluation results |
| Integrity | SHA-256 fingerprint للـ manifest |

عند استخدام نفس المدخلات والتكوين والزمن المحدد، ينتج manifest بنفس fingerprint، ويمكن مقارنة fingerprint بين تشغيلين بدل الاعتماد على الذاكرة أو أسماء الملفات.

## Training وEvaluation

يحافظ العامل على حالات `queued`, `validating`, `preparing`, `running`, `evaluating`, `completed`, `failed`, و`cancelled`، مع heartbeat وworker id وprogress. بعد التدريب ينشر artifact، ثم يمرر samples إلى `EvaluationEngine`، الذي يحسب intent/entity metrics، confusion matrix، per-intent metrics، confidence correctness، fallback rate، وquality gate decision.

لا يسمح `QualityGate` بترقية نموذج يفتقد artifact أو يفشل thresholds المحددة. وتضاف نتيجة البوابة إلى evaluation report بدل إخفائها داخل log نصي.

## Error Analysis وإعادة التدريب

تقوم `ErrorAnalyzer` باستخراج كل intent mismatch، confidence المنخفض، confusion pairs، وعدد الأخطاء لكل intent. يحول `RetrainingPlanner` التقرير إلى خطة structured تتضمن إضافة أمثلة مصححة، مراجعة entity annotations، مراجعة confusion pairs، ومراجعة low-confidence examples ثم إعادة التقسيم دون leakage.

يضم العامل التقرير داخل Model Version، لذلك يصبح قرار إعادة التدريب مرتبطًا مباشرة بالإصدار الذي سببه، وليس بملاحظة خارجية غير قابلة للتتبع.

## Model Registry وDeployment

يحتوي `ModelRegistry` على model_id وversion وproject_id وdataset_version وtraining_job_id وartifact checksum وevaluation report وquality gate. يحل aliases باستخدام `(project_id, environment, alias)`، فلا يوجد model hardcoded ولا يمكن لمشروع الوصول إلى نموذج مشروع آخر.

تم تصحيح deployment history ليخزن الزوج الكامل `(model_id, version)` بدل version منفردة. هذا يمنع rollback من إعادة نسخة خاطئة عندما يتغير model_id داخل نفس المشروع والبيئة. كما يتحقق registry من أن النموذج ready وأن project_id متطابق قبل إنشاء alias.

## التحقق

تم تشغيل:

```bash
python3 -m compileall -q framework tests
pytest -q
```

والنتيجة الأخيرة هي **91 passed, 2 skipped**. التحذيرات الموجودة هي تحذيرات deprecation من FastAPI/Starlette ولا تمثل فشلًا في Specification 07.

## Commits

- `00ae055` — إضافة massive dataset ingestion وcleaning وconversation context.
- `af5634a` — إضافة reproducible training وerror analysis وretraining planning.
- الإصلاح الحالي يضمن model registry rollback الصحيح مع cross-model deployment history.
