import pytest
from pydantic import ValidationError

from prepify.generation.copyright import enforce_paraphrase
from prepify.schemas import MCQ, QuestionExplainRequest
from prepify.topics import resolve_topic


def test_mcq_requires_exactly_four_unique_options() -> None:
    with pytest.raises(ValidationError):
        MCQ(
            question_text="Which statement is correct?",
            options=["A", "A", "B", "C"],
            correct_option_index=0,
            topic_tag="Recursion",
            difficulty="Hard",
            source_chunk_ids=["chunk-1"],
        )


def test_check_answer_requires_student_text() -> None:
    with pytest.raises(ValidationError):
        QuestionExplainRequest(mode="check_answer")


def test_official_topic_tier_drives_default_difficulty() -> None:
    assert resolve_topic("10.4").name == "Introduction to Abstract Data Types (ADT)"
    assert resolve_topic("10.4").difficulty == "Medium"
    assert resolve_topic("Recursion").difficulty == "Hard"


def test_long_verbatim_copy_is_rejected() -> None:
    source = "A" * 150 + " source tail"
    with pytest.raises(ValueError, match="paraphrase guard"):
        enforce_paraphrase(["A" * 150], [source])

