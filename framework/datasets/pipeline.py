from dataclasses import dataclass
from framework.datasets.system import DatasetValidator, DatasetVersion, TrainingExample

@dataclass
class QualityReport:
    total: int
    valid: int
    duplicate_count: int
    intent_distribution: dict[str, int]
    errors: list[str]

class DatasetPipeline:
    def __init__(self, validator: DatasetValidator | None = None): self.validator = validator or DatasetValidator()
    def normalize(self, examples: list[TrainingExample]) -> list[TrainingExample]:
        return [TrainingExample(text=" ".join(example.text.split()), intent=example.intent.strip(), entities=example.entities, metadata=example.metadata) for example in examples]
    def deduplicate(self, examples: list[TrainingExample]) -> list[TrainingExample]:
        seen: set[tuple[str, str]] = set(); result = []
        for example in examples:
            key = (example.text, example.intent)
            if key not in seen: seen.add(key); result.append(example)
        return result
    def quality(self, examples: list[TrainingExample], known_intents: set[str], known_entities: set[str]) -> QualityReport:
        normalized = self.normalize(examples)
        unique = self.deduplicate(normalized)
        errors = self.validator.validate(unique, known_intents, known_entities)
        distribution: dict[str, int] = {}
        for example in unique: distribution[example.intent] = distribution.get(example.intent, 0) + 1
        return QualityReport(len(normalized), len(unique) - len(errors), len(normalized) - len(unique), distribution, errors)
    def prepare(self, dataset: DatasetVersion, known_intents: set[str], known_entities: set[str]) -> tuple[DatasetVersion, QualityReport]:
        normalized = self.normalize(list(dataset.examples))
        examples = self.deduplicate(normalized)
        errors = self.validator.validate(examples, known_intents, known_entities)
        distribution: dict[str, int] = {}
        for example in examples: distribution[example.intent] = distribution.get(example.intent, 0) + 1
        report = QualityReport(len(normalized), len(examples) - len(errors), len(normalized) - len(examples), distribution, errors)
        if report.errors: raise ValueError(f"Dataset quality checks failed: {report.errors}")
        return DatasetVersion(dataset.dataset_id, dataset.version, dataset.project_id, tuple(examples), dataset.schema_version, "validated", dataset.created_at), report
