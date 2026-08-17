from framework.learning.continuous import CandidateStatus, InteractionCollectionService, SampleStatus


def test_interactions_are_redacted_and_not_training_candidates_automatically():
    service = InteractionCollectionService(low_confidence_threshold=0.55, high_confidence_error_threshold=0.9)
    interaction = service.collect(project_id="p1", session_id="s1", language="ar", input_text="مرحبا bot_token=[REDACTED_TEST_TOKEN]", predicted_intent="greet", confidence=0.4, metadata={"api_key": "private"})
    assert "8996700328:" not in interaction.input_text and interaction.metadata["api_key"] == "[REDACTED]"
    assert service.list_candidates("p1") == []


def test_candidate_lifecycle_requires_approval_before_promotion_and_is_project_isolated():
    service = InteractionCollectionService()
    interaction = service.collect(project_id="p1", session_id="s1", language="en", input_text="cancel my order", predicted_intent="cancel_order", confidence=0.93)
    candidate = service.candidate_from_interaction(interaction.interaction_id, project_id="p1")
    try:
        service.transition_candidate(candidate.sample_id, project_id="p2", status=CandidateStatus.APPROVED, sample_status=SampleStatus.APPROVED)
        assert False
    except KeyError:
        pass
    try:
        service.transition_candidate(candidate.sample_id, project_id="p1", status=CandidateStatus.PENDING, sample_status=SampleStatus.PROMOTED)
        assert False
    except ValueError:
        pass
    service.transition_candidate(candidate.sample_id, project_id="p1", status=CandidateStatus.APPROVED, sample_status=SampleStatus.APPROVED)
    promoted = service.transition_candidate(candidate.sample_id, project_id="p1", status=CandidateStatus.APPROVED, sample_status=SampleStatus.PROMOTED)
    assert promoted.sample_status == SampleStatus.PROMOTED


def test_low_confidence_and_high_confidence_error_queues_are_distinct():
    service = InteractionCollectionService(low_confidence_threshold=0.55, high_confidence_error_threshold=0.9)
    low = service.collect(project_id="p1", session_id=None, language="ar", input_text="x", predicted_intent="a", confidence=0.2)
    high = service.collect(project_id="p1", session_id=None, language="ar", input_text="y", predicted_intent="a", confidence=0.97)
    assert [item.interaction_id for item in service.low_confidence("p1")] == [low.interaction_id]
    assert [item.interaction_id for item in service.high_confidence_errors("p1", known_correct_intents={high.interaction_id: "b"})] == [high.interaction_id]


def test_duplicate_candidate_is_flagged_without_deleting_original():
    service = InteractionCollectionService()
    first = service.collect(project_id="p1", session_id=None, language="en", input_text="hello", predicted_intent="greet", confidence=0.6)
    second = service.collect(project_id="p1", session_id=None, language="en", input_text="hello", predicted_intent="greet", confidence=0.6)
    a = service.candidate_from_interaction(first.interaction_id, project_id="p1")
    b = service.candidate_from_interaction(second.interaction_id, project_id="p1")
    assert a.sample_id == b.sample_id and b.status == CandidateStatus.DUPLICATE


def test_data_quality_and_hard_example_clustering_are_explainable():
    from framework.learning.intelligence import DataQualityEngine, HardExampleEngine
    service = InteractionCollectionService()
    first = service.collect(project_id="p1", session_id=None, language="ar", input_text="عايز حالة الطلب", predicted_intent="status", confidence=0.97)
    second = service.collect(project_id="p1", session_id=None, language="ar", input_text="حالة", predicted_intent="status", confidence=0.2)
    candidate = service.candidate_from_interaction(first.interaction_id, project_id="p1")
    quality = DataQualityEngine().sample(candidate, known_intents={"status"})
    hard = HardExampleEngine().detect([first, second], known_correct_intents={first.interaction_id: "cancel"})
    clusters = HardExampleEngine().cluster(hard)
    assert quality.score > 0 and quality.correctness == 1.0
    assert any(item.reason == "high_confidence_error" for item in hard)
    assert "cancel_vs_status" in clusters


def test_human_review_creates_annotation_versions_and_open_conflict():
    from framework.learning.review import HumanReviewService, ReviewDecision
    service = HumanReviewService()
    first = service.review(project_id="p1", sample_id="s1", reviewer_id="r1", decision=ReviewDecision.CORRECT, corrected_intent="refund", notes="review one")
    second = service.review(project_id="p1", sample_id="s1", reviewer_id="r2", decision=ReviewDecision.CORRECT, corrected_intent="cancel_order", notes="review two")
    assert first.annotation_version == 1 and second.annotation_version == 2
    conflicts = service.list_conflicts("p1")
    assert len(conflicts) == 1 and conflicts[0].status == "open"
    resolved = service.resolve(conflicts[0].conflict_id, project_id="p1", resolver_id="senior", intent="refund")
    assert resolved.status == "resolved" and "senior_reviewer:senior:refund" == resolved.resolution


def test_feedback_is_not_ground_truth_and_promotion_requires_gates():
    from framework.learning.policy import DatasetPromotionPolicy, FeedbackService, FeedbackType, ProductionPromotionPolicy, ContinuousTrainingOrchestrator
    feedback = FeedbackService().record(project_id="p1", interaction_id="i1", feedback_type=FeedbackType.CORRECTION, intent="cancel_order")
    assert feedback.trusted is False
    policy = DatasetPromotionPolicy(minimum_quality=80, minimum_review_rate=.8, maximum_duplicate_rate=.1)
    assert policy.evaluate(quality_score=90, review_rate=.9, duplicate_rate=.02, verified_count=9, total_count=10)[0]
    decision = ProductionPromotionPolicy().decide(quality_passed=True, regression_passed=False, human_approved=False)
    assert decision.recommendation == "REJECT" and not decision.passed
    orchestrator = ContinuousTrainingOrchestrator(minimum_approved_examples=2)
    assert orchestrator.should_trigger(trigger="data_threshold", approved_count=2, error_count=0, dataset_fingerprint="a")[0]
    assert not orchestrator.should_trigger(trigger="data_threshold", approved_count=2, error_count=0, dataset_fingerprint="a")[0]


def test_training_data_firewall_blocks_secrets_and_requires_reviewed_sanitized_data():
    from datetime import datetime, timedelta, timezone
    from framework.learning.safety import RetentionPolicy, TrainingDataFirewall
    firewall = TrainingDataFirewall()
    try:
        firewall.sanitize(text="api_key=supersecret")
        assert False
    except ValueError as exc:
        assert str(exc) == "TRAINING_DATA_SECRET_DETECTED"
    sanitized = firewall.sanitize(text="contact me at user@example.com")
    assert sanitized["pii_redacted"] and "EMAIL_REDACTED" in sanitized["text"]
    firewall.assert_approved(sample_status="approved", review_status="human_verified", sanitized=True)
    assert RetentionPolicy(retention_days=1).expired(datetime.now(timezone.utc) - timedelta(days=2))
