# Specification 04 Compliance Checklist

## Scope

This checklist tracks the implementation of **Developer Platform, API Gateway, Developer SDK & Telegram Runtime** against `/home/ubuntu/upload/pasted_content.txt`.

| Specification areas | Current state before Phase 4 work | Target |
|---|---|---|
| API Gateway, auth, project resolution, authorization | Partially present in FastAPI helpers and route-level checks | Centralized gateway context with API-key/project/permission/rate-limit/usage handling |
| API keys | Creation, hashing, rotation/revocation primitives exist | Real CRUD metadata, key types, expiry, permissions, safe responses |
| Messages API | Basic route exists | Standard response, metadata/session, idempotency, error registry |
| Python SDK | Missing | Sync and async clients, resources, typed errors, retry policy |
| Webhooks | Missing as developer resource | Signed registration, delivery, retries, idempotency, logs |
| Telegram platform | Basic bot CRUD/webhook route exists | Secure credential abstraction, validate/connect/disconnect/status, runtime flow |
| Actions/tools/extensions | Core action/tool registries exist | Developer-facing registry contracts and API |
| Model selection/runtime | Phase 3 runtime exists | Project/environment model selection through runtime abstraction |
| Usage/rate limits/quotas | Basic usage and limiter exist | API-key/project/endpoint dimensions, quota abstraction, dashboard data |
| Documentation | FastAPI OpenAPI exists | SDK docs, quick starts, examples, error documentation |
| Security/E2E/performance | Partial tests exist | Specification 04 matrix and no-secret/no-IDOR tests |

## Definition of Done

- [ ] Create project → create API key → use Python SDK → POST messages → standardized response.
- [ ] Register Telegram bot → validate/connect → select model → receive Telegram update → Core Engine → response.
- [ ] Create dataset → train → evaluate → deploy → use selected model.
- [ ] No public API bypasses the Gateway context.
- [ ] No raw API key, Telegram token, webhook secret, or hashed secret appears in responses/logs.
- [ ] All resources remain project-scoped.
- [ ] Full automated test matrix passes.
