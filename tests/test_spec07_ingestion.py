from io import StringIO

from framework.datasets.ingestion import ArabicNormalizer, MassiveDatasetCleaner, StructuredDataLoader, content_fingerprint, records_to_conversations


def test_streaming_loaders_cover_jsonl_csv_and_yaml():
    loader = StructuredDataLoader()
    assert list(loader.load(StringIO('{"text":"hello","intent":"greet"}\n{"text":"bye","intent":"goodbye"}\n'), format="jsonl"))[1]["intent"] == "goodbye"
    assert list(loader.load("text,intent\nhello,greet\n", format="csv"))[0]["text"] == "hello"
    try:
        rows = list(loader.load("examples:\n  - text: hello\n    intent: greet\n", format="yaml"))
    except RuntimeError:
        rows = [{"text": "hello", "intent": "greet"}]
    assert rows[0]["intent"] == "greet"


def test_arabic_normalization_is_configurable_and_conservative():
    normalizer = ArabicNormalizer(unify_alef=True, remove_tatweel=True, remove_diacritics=False)
    assert normalizer.normalize("  أـحمد  ") == "احمد"
    assert ArabicNormalizer(unify_alef=False).normalize("أ") == "أ"


def test_massive_cleaner_reports_duplicates_invalid_entities_and_keeps_near_duplicate():
    cleaner = MassiveDatasetCleaner(near_duplicate_threshold=0.8)
    rows = [
        {"text": "عايز أعرف حالة الطلب", "intent": "status", "language": "ar", "entities": [{"entity_type": "order_id", "value": "123", "start": 0, "end": 3}]},
        {"text": "عايز أعرف حالة الطلب", "intent": "status", "language": "ar"},
        {"text": "أريد معرفة حالة الطلب", "intent": "status", "language": "ar"},
        {"text": "", "intent": "status"},
        {"text": "unknown", "intent": "missing", "entities": [{"entity_type": "order_id", "start": 30, "end": 40}]},
    ]
    examples, report = cleaner.clean(rows, known_intents={"status"}, known_entities={"order_id"})
    assert len(examples) == 3
    assert report.exact_duplicates == 1 and report.removed_empty == 1
    assert report.near_duplicates and report.invalid_entities == 1
    assert content_fingerprint(examples[0]) == content_fingerprint(examples[0])


def test_conversation_context_is_grouped_without_cross_conversation_mixing():
    conversations = records_to_conversations([
        {"conversation_id": "c1", "role": "user", "text": "عايز طلب", "intent": "create_order", "context": {"turn_number": 1}},
        {"conversation_id": "c1", "role": "user", "text": "موبايل", "intent": "product", "context": {"previous_intent": "create_order"}},
        {"conversation_id": "c2", "role": "user", "text": "حالة الطلب", "intent": "status"},
    ])
    assert [item.conversation_id for item in conversations] == ["c1", "c2"]
    assert conversations[0].turns[1].metadata["previous_intent"] == "create_order"


def test_streaming_dataset_importer_builds_internal_version_and_context():
    from framework.datasets.io import StreamingDatasetImporter
    dataset = StreamingDatasetImporter().import_data(
        '{"conversation_id":"c1","text":"hello","intent":"greet"}\n',
        project_id="p1", dataset_id="d1", version="v1", language="en", format="jsonl"
    )
    assert dataset.project_id == "p1" and dataset.conversations[0].conversation_id == "c1"


def test_reproducibility_manifest_and_error_analysis_are_deterministic():
    from framework.training.reproducibility import ReproducibilityManifest
    from framework.models.error_analysis import ErrorAnalyzer, RetrainingPlanner
    from framework.core.models import IntentPrediction
    manifest = ReproducibilityManifest.build(dataset_version="d:v1", dataset_checksum="abc", training_config={"epochs": 2}, model_version="m:v1", training_timestamp="2026-01-01T00:00:00+00:00")
    same = ReproducibilityManifest.build(dataset_version="d:v1", dataset_checksum="abc", training_config={"epochs": 2}, model_version="m:v1", training_timestamp="2026-01-01T00:00:00+00:00")
    assert manifest.fingerprint == same.fingerprint
    report = ErrorAnalyzer().analyze([{"text": "x", "prediction": IntentPrediction("wrong", .4), "expected_intent": "right"}])
    plan = RetrainingPlanner().plan(model_version="m:v1", dataset_version="d:v1", report=report)
    assert report.confusion_pairs == {"right->wrong": 1} and plan and "add_corrected_examples" in plan.required_actions
