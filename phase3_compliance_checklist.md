# Phase 3 Compliance Checklist

## Definition of Done

| Requirement | Initial evidence | Status |
|---|---|---|
| Create Dataset | `POST /api/v1/datasets`, `DatasetRegistry.create` | Implemented, but API persistence models each version as a row rather than a separate Dataset aggregate |
| Create immutable Dataset Version | `DatasetRegistry.publish`, frozen dataclasses, API version lineage | Partial: domain registry enforces immutability; API persistence still represents versions as rows and needs a separate Dataset aggregate for strict database-level immutability |
| Add/Import Examples | JSON/JSONL/CSV importers and `POST /api/v1/datasets/{id}/import` | Implemented for JSON/JSONL/CSV |
| Validate Dataset | `DatasetPipeline`, `/validate` | Implemented |
| Quality Report | `QualityReport` | Implemented |
| Statistics | `DatasetPipeline.statistics`, `/statistics` | Implemented |
| Duplicate detection | Exact and near duplicate functions | Implemented, but near duplicates are warnings only |
| Conflict detection | `find_conflicts` | Implemented |
| Dataset splitting | Conversation-safe deterministic intent-aware split | Implemented |
| Rasa export | `RasaExporter` and production provider wiring | Provider path is wired; real CLI execution remains environment-dependent because Rasa CLI is not installed in sandbox |
| Training job/worker | API, Redis queue, worker | Implemented |
| Real Rasa provider | `RasaTrainingProvider` and CLI invocation | Implemented, requires local Rasa executable |
| Model artifact | artifact service and checksum | Implemented in worker path |
| Evaluation/report | `EvaluationEngine` | Implemented when explicit evaluation samples exist |
| Register model/READY | Model ORM, worker QualityGate, evaluation report and runtime state | Implemented for the training path; direct registry creation remains `created` until evaluation/QualityGate is run |
| Environment deploy | deployment endpoint | Implemented, but legacy deployment endpoint remains a second path |
| Rollback | persisted deployment history and endpoint | Implemented, requires at least two deployment events |
| Dataset→Training→Model lineage | IDs, checksums, audit events, worker loader | Partial: lineage is tracked, but API persistence still conflates Dataset aggregate and version rows |

## Additional specification gaps found

1. Intent and Entity taxonomy types are not present in the dataset layer.
2. Review provenance fields `reviewed_by`, `reviewed_at`, and `review_notes` are not persisted as first-class fields.
3. Evaluation/test split and leakage prevention are not fully wired into TrainingJob creation.
4. Threshold optimization, model comparison, and model runtime/cache lifecycle are implemented as services with API/RBAC/audit integration; hard-set/regression orchestration remains limited to the existing evaluation contract.
5. Dataset audit events for create/version/import/validate/training/model/deploy/rollback are not consistently emitted.
6. The core engine has trace and idempotency, but it does not persist the updated session/context through a repository-backed state manager in `process_message`.
7. The API persistence model still uses the existing `datasets` table as version rows; a separate persisted Dataset aggregate/current-version relation is not yet enforced.
8. Rasa CLI is not installed in the current sandbox, so the real local Rasa training command cannot be executed here; the production provider now invokes it when installed.
9. The three deferred services are now implemented: threshold optimization, model comparison, and model runtime/cache lifecycle. Hard-set/regression orchestration remains limited to explicit evaluation inputs.
