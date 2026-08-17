# Phase 2 Specification Audit

## Current baseline

المشروع يحتوي على Foundation فعلية تشمل FastAPI وPostgreSQL/Redis adapters وAPI auth وTelegram adapter وRasa HTTP provider وregistries وevent bus وsession state وFrameworkEngine أولي. لكن Engine الحالي يعتمد على `detect_intent`/`extract_entities` بدل `NLUResult.analyze`، ولا يملك `ProcessingContext` و`RequestContext` و`PolicyResult` و`ResponseBuilder` كعقود موحدة، كما أن event metadata والـ timing والـ error isolation ليست مكتملة.

## Priority gaps mapped to specification

| Spec sections | Gap | Planned real implementation |
|---|---|---|
| 4-8, 42-44 | Core context/result/pipeline contracts ناقصة | Implemented: ProcessingContext وRequestContext وNLUResult وPolicyResult وActionContext/ActionResult وProcessingResult serialization وstage timings وApplication Service. |
| 8-11, 14-16 | NLU abstraction تستخدم API قديمًا وRasa error normalization ناقص | Implemented: `NLUProvider.analyze` compatibility contract، Rasa normalized NLUResult، retry/timeout، NLUProviderError، ConfidencePolicy وEntityNormalizer. |
| 17-24 | Session/context/dialogue/conversation/user/channel identity غير ممثلة بالكامل | Implemented: Session lifecycle كامل، ContextManager، ConversationManager، UserResolver، ChannelIdentity، وPersistentSession compatibility. |
| 26-36 | Policy/action/tool/response contracts مبسطة | Implemented: PolicyResult decisions، ActionContext/ActionResult، Action/Tool registry validation، tool authorization/timeout، وResponseBuilder channel-agnostic. |
| 37-44 | Event metadata/isolation/middleware/timing ناقصة | Implemented: typed FrameworkEvent metadata، handler isolation، ProcessingMiddlewareChain، named stage timings، وCore events المطلوبة. |
| 48-50 | Plugin API لا يملك PluginContext وregistry/event registration الكامل | Implemented: PluginContext محدود الصلاحيات، registries validation، PluginRuntime timeout/error isolation، وPluginLoader dependency lifecycle. |
| 51-54 | idempotency/message persistence contracts ناقصة | Implemented: IdempotencyStore abstraction وInMemory fallback وRedisIdempotencyStore عند توفر Redis قبل action execution. |
| 55-61 | Core E2E FakeNLU/FakeAction/Rasa adapter contract غير مكتمل | Implemented: FakeNLUProvider وEchoAction test contract وCore E2E بدون Telegram/Rasa، مع RasaProvider normalized interface للاختبار الخارجي عند توفره. |
| 64-70 | API message route لا يمر عبر Application Service موحد وcomponent health ناقص | Implemented: MessageApplicationService، readiness لـ DB/Redis/S3/Secret Manager/NLU/Telegram، وSettings thresholds/timeouts/rate limit. |
| 71-77 | المرحلة الثانية يجب أن تثبت runtime/core لا training expansion | إبقاء training platform الحالية خارج pipeline الجديدة، وتوثيق حدودها. |

## Acceptance scenario

المعيار الأساسي هو تشغيل `IncomingMessage -> FrameworkEngine -> Session/Context -> NLUProvider -> Intent/Entity resolution -> Dialogue -> Policy -> Action -> ResponseBuilder -> ProcessingResult` باستخدام provider/action قابلين للاستبدال، ثم تشغيل نفس العقود مع RasaProvider وTelegramAdapter دون أن يعرف Core أيًا منهما.
