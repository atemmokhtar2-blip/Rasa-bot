import pytest
from framework.datasets.system import ConversationExample, ConversationTurn, DatasetRegistry, DatasetStatus, DatasetVersion, EntityAnnotation, TrainingExample
from framework.datasets.pipeline import DatasetPipeline

def examples():
    return [TrainingExample('عايز أعرف حالة الطلب', 'get_order_status', ({'entity_type': 'order_id', 'value': '123', 'start': 20, 'end': 23},), language='ar', conversation_id='c1'), TrainingExample('cancel order', 'cancel_order', language='en', conversation_id='c2'), TrainingExample('status', 'get_order_status', language='en', conversation_id='c3')]

def test_dataset_and_immutable_version_with_checksum():
    registry = DatasetRegistry(); dataset = registry.create('p1', 'support', language='ar')
    version = registry.publish(registry.create_version(dataset.dataset_id, 'v1', examples(), created_by='dev-1'))
    assert version.status == 'published' and version.checksum and len(version.checksum) == 64
    assert registry.get_dataset(dataset.dataset_id).current_version == 'v1'
    with pytest.raises(ValueError): registry.publish(version)
    assert registry.get_dataset(dataset.dataset_id).status == DatasetStatus.READY

def test_entity_annotation_and_quality_report():
    annotation = EntityAnnotation.from_dict({'entity_type': 'order_id', 'value': '123', 'start': 0, 'end': 3})
    assert annotation.to_dict()['entity_type'] == 'order_id'
    pipeline = DatasetPipeline()
    report = pipeline.quality(examples() + [examples()[0]], {'get_order_status', 'cancel_order'}, {'order_id'})
    assert report.duplicate_count == 1 and report.statistics['total_intents'] == 2 and report.quality_score > 0

def test_conflict_and_conversation_safe_split():
    pipeline = DatasetPipeline()
    conflicting = [TrainingExample('الغيه', 'cancel_order', conversation_id='c1'), TrainingExample('الغيه', 'cancel_booking', conversation_id='c2')]
    report = pipeline.quality(conflicting, {'cancel_order', 'cancel_booking'}, set())
    assert report.conflict_count == 1
    turns = (ConversationTurn('user', 'عايز أحجز', 'book'), ConversationTurn('user', 'بكرة', 'date'))
    conversation = ConversationExample('conversation-1', turns)
    split = pipeline.split([TrainingExample('book', 'book', conversation_id=conversation.conversation_id), TrainingExample('date', 'date', conversation_id=conversation.conversation_id)], 0.5, 0.25, 0.25)
    assert sum(len(part) for part in (split.train, split.validation, split.test)) == 2
    assert not ({e.conversation_id for e in split.train} & {e.conversation_id for e in split.test})

def test_prepared_checksum_matches_deduplicated_normalized_content():
    pipeline = DatasetPipeline()
    dataset = DatasetRegistry().create('p1', 'checksum')
    checksum_examples = [TrainingExample('order status', 'get_order_status', language='en'), TrainingExample('cancel order', 'cancel_order', language='en'), TrainingExample('order status', 'get_order_status', language='en')]
    version = DatasetVersion(dataset.dataset_id, 'v1', 'p1', tuple(checksum_examples))
    prepared, _ = pipeline.prepare(version, {'get_order_status', 'cancel_order'}, set())
    assert prepared.checksum == prepared.calculate_checksum()
    assert len(prepared.examples) == 2


def test_split_is_deterministic_and_keeps_conversation_groups_intact():
    pipeline = DatasetPipeline()
    items = [TrainingExample(f'text-{index}', 'intent-a' if index % 2 else 'intent-b', conversation_id=f'conversation-{index // 2}') for index in range(12)]
    first = pipeline.split(items, 0.6, 0.2, 0.2, seed=7)
    second = pipeline.split(items, 0.6, 0.2, 0.2, seed=7)
    assert first == second
    locations = {}
    for name, bucket in (("train", first.train), ("validation", first.validation), ("test", first.test)):
        for item in bucket:
            assert item.conversation_id not in locations or locations[item.conversation_id] == name
            locations[item.conversation_id] = name
