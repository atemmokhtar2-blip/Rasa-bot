# Implementation Specification 08

## Continuous Learning, Human Feedback & Dataset Intelligence

تضيف هذه المرحلة حلقة تعلم مستمر فوق Training Infrastructure في Specification 07. المسار الآمن هو:

> Runtime → Interaction Telemetry → Candidate Sample → Filtering → Human Review → Annotation Version → Dataset Version → Training → Evaluation → Regression Gate → Model Candidate → Promotion Policy → Production

لا يقوم Runtime بتعديل Production Model مباشرة، ولا تعتبر كل Interaction أو User Feedback بيانات تدريب تلقائيًا.

## Interaction Collection

يقدم `InteractionCollectionService` سجلًا project-scoped يحتوي interaction id، session، language، input، prediction، confidence، entities، response، model version، processing time، status، وmetadata. يمر النص والـ metadata عبر `PrivacyRedactor` قبل التخزين، مع إزالة Bot Tokens وAPI Keys وBearer credentials والحقول الحساسة المعروفة.

الـ API هو `POST /api/v1/learning/interactions`. إنشاء Candidate منفصل ويتم عبر `POST /api/v1/learning/candidates`. هذا الفصل يمنع انتقال Raw Runtime Data إلى التدريب.

## Candidate lifecycle

كل Candidate يحمل status مستقلًا عن sample lifecycle. الحالات المدعومة هي `pending`, `reviewing`, `approved`, `rejected`, و`duplicate`، بينما sample lifecycle هو `collected`, `filtered`, `pending_review`, `approved`, `rejected`، و`promoted`.

لا يسمح النظام بترقية Candidate إلى `promoted` إلا إذا كان `approved`. وتُعلّم التكرارات على أنها duplicate بدل حذف الأصل، مع fingerprint project-scoped لمنع خلط بيانات المشاريع.

## Human Review وAnnotation Versioning

يسجل `HumanReviewService` كل قرار Review مع reviewer id، decision، corrected intent، corrected entities، notes، وannotation version. القرارات `approve`, `reject`, و`correct` منفصلة عن Runtime.

كل تصحيح ينتج `AnnotationVersion` جديدة مع parent version، ولا يتم تعديل التاريخ السابق. إذا اختلف Reviewerان في intent، ينشئ النظام `ReviewConflict` ولا يعتمد أول Reviewer تلقائيًا.

يتم حل التعارض عبر `ConflictResolver` بسياسة صريحة مثل `senior_reviewer`, `consensus`, أو `rule`. لا يسمح resolver باختيار intent خارج مجموعة intents المتعارضة.

## Feedback

يدعم `POST /api/v1/feedback` الأنواع `thumb_up`, `thumb_down`, `correction`, `explicit_intent`, و`human_review`. Feedback المستخدم ليس Ground Truth تلقائيًا؛ الحقل `trusted` لا يصبح صحيحًا إلا بقرار موثوق من policy أو reviewer.

كل Feedback project-scoped، ويمنع المسار الوصول إلى بيانات مشروع آخر. تحفظ correction candidates في مسار المراجعة نفسه بدل إرسالها مباشرة إلى Training.

## Data Quality وHard Examples

يحسب `DataQualityEngine` درجات تفسيرية لـ completeness، correctness، consistency، duplication، diversity، annotation quality، intent balance، وentity quality. لا يعتمد score على رقم عشوائي؛ كل component مشتق من قواعد معلنة، ويظهر `reasons` عند فشل العينة.

يكتشف `HardExampleEngine` low-confidence samples، high-confidence errors، intent confusion، ويصنفها إلى clusters مثل `refund_vs_cancel_order`. هذا يختصر آلاف الأخطاء في أنماط قابلة للمراجعة وتحسين Dataset.

## Continuous Training Policies

تحدد `DatasetPromotionPolicy` minimum quality، minimum review rate، maximum duplicate rate، ومتطلبات human verification. وتحدد `ContinuousTrainingOrchestrator` triggers manual، data threshold، error threshold، وscheduled مع cooldown يعتمد على Dataset fingerprint.

إذا لم يتغير fingerprint منذ آخر Training، يعيد orchestrator `dataset_unchanged` ولا ينشئ Job مكررًا. Scheduled training ليس مفروضًا افتراضيًا.

## Training Data Firewall وData Safety

يوفر `TrainingDataFirewall` طبقة إلزامية قبل وصول Candidate إلى Dataset أو Training. يكتشف API keys وBot tokens وpasswords وBearer credentials، ويرفض الأسرار بدل تخزينها. كما يوفر `PIIDetector` و`PIIRedactor` استعدادًا لمعالجة البريد الإلكتروني وأرقام الهاتف، مع حفظ metadata يوضح أن النص تمت معالجته.

لا يسمح firewall بالعبور إلا عندما تكون العينة `approved`، وReview status موثوقًا، ومرحلة sanitization مكتملة. وتوفر `RetentionPolicy` حدًا زمنيًا قابلًا للتهيئة لبيانات Runtime، مع خيار حذف البيانات الخام بعد promotion.

## Production Safety

تستخدم `ProductionPromotionPolicy` ثلاث نتائج: `PROMOTE`, `HOLD`, و`REJECT`. لا يسمح Promotion إلى production عند فشل Quality Gate أو اكتشاف Regression. كما يتطلب human approval ما لم يُفعّل `auto_deploy` صراحةً.

مسار Deployment يقرأ evaluation report وquality gate وregression result قبل تغيير alias. هذه السياسة تمنع المسار غير الآمن:

```text
User Message → Automatic Training → Automatic Production Deployment
```

وتفرض المسار:

```text
Candidate → Filter → Sanitize → Review → Approved → Dataset Version
→ Training → Evaluation → Regression → Quality Gate → Promotion Policy
```

## Endpoints

| Endpoint | الغرض |
|---|---|
| `POST /api/v1/learning/interactions` | تسجيل Interaction آمن |
| `POST /api/v1/learning/candidates` | تحويل Interaction إلى Candidate |
| `GET /api/v1/projects/{project_id}/learning/candidates` | عرض Candidates project-scoped |
| `POST /api/v1/learning/candidates/{sample_id}/transition` | نقل Candidate بين الحالات |
| `POST /api/v1/learning/reviews` | إنشاء Human Review وAnnotation Version |
| `GET /api/v1/projects/{project_id}/learning/conflicts` | عرض التعارضات المفتوحة |
| `POST /api/v1/learning/conflicts/{conflict_id}/resolve` | حل التعارض بسياسة محددة |
| `POST /api/v1/feedback` | تسجيل User/Developer Feedback كمرشح |
| `GET /api/v1/projects/{project_id}/feedback` | عرض Feedback للمشروع |

## التحقق

تم تشغيل compile check وpytest بعد دمج طبقات Specification 08. النتيجة الحالية هي **99 passed, 2 skipped**، مع تحذيرات deprecation من FastAPI/Starlette فقط، ولا توجد أخطاء اختبار.
