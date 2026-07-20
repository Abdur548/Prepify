from types import SimpleNamespace

from prepify.config import settings
from prepify.generation.explainer import QuestionExplainerService
from prepify.generation.mcq import MCQService
from prepify.retrieval.retriever import RetrievedChunk
from prepify.schemas import MCQGenerateResponse, QuestionExplainRequest


class FakeRepository:
    def __init__(self) -> None:
        self.events = []

    def log_event(self, event_type, **kwargs) -> None:
        self.events.append((event_type, kwargs))

    def get_question(self, question_id):
        return SimpleNamespace(
            id=question_id,
            question_number="6(a)",
            topic_tag="Recursion",
            linked_mark_scheme_id="ms-doc",
            linked_insert_id="insert-doc",
        )


class FakeRetriever:
    def retrieve(self, query, *, collection, filters=None, top_k=None):
        if collection == settings.question_collection and filters.get("source_type") == "question":
            return [
                RetrievedChunk(
                    "q-1",
                    "A recursive routine needs a base case and a recursive case.",
                    0.9,
                    {"source_type": "question", "document_id": "qp-doc"},
                )
            ]
        if collection == settings.mark_scheme_collection:
            return [
                RetrievedChunk(
                    "ms-1",
                    "Credit an explanation that identifies the stopping condition.",
                    0.95,
                    {
                        "source_type": "mark_scheme",
                        "document_id": "ms-doc",
                        "question_id": "question-1",
                        "page_number": 5,
                        "point_label": "MP1",
                    },
                )
            ]
        if filters.get("source_type") == "insert":
            return [
                RetrievedChunk(
                    "insert-1",
                    "A short supplied dataset.",
                    0.7,
                    {"source_type": "insert", "document_id": "insert-doc"},
                )
            ]
        return [
            RetrievedChunk(
                "q-1",
                "A question asks the learner to explain a recursive stopping condition.",
                0.8,
                {
                    "source_type": "question",
                    "document_id": "qp-doc",
                    "question_id": "question-1",
                },
            )
        ]


class FakeLLM:
    def generate(self, *, system, prompt, schema):
        if schema is MCQGenerateResponse:
            return schema.model_validate(
                {
                    "questions": [
                        {
                            "question_text": "What prevents recursive calls from continuing forever?",
                            "options": [
                                "A stopping condition",
                                "A global variable",
                                "A second loop",
                                "A larger input",
                            ],
                            "correct_option_index": 0,
                            "topic_tag": "Recursion",
                            "difficulty": "Medium",
                            "source_chunk_ids": ["q-1"],
                        }
                    ]
                }
            )
        return schema.model_validate(
            {
                "explanation": "Focus on why the calls eventually stop.",
                "reasoning_steps": [
                    "Identify the condition checked by each call.",
                    "Show how the input moves toward that condition.",
                ],
                "answer_feedback": "Your response should make the stopping condition explicit.",
            }
        )


def test_mcq_service_preserves_internal_grounding_ids() -> None:
    repository = FakeRepository()
    result = MCQService(
        repository,
        retriever=FakeRetriever(),
        llm=FakeLLM(),
    ).generate("Recursion", 1)

    assert result.questions[0].source_chunk_ids == ["q-1"]
    assert repository.events[0][0] == "mcq_generated"


def test_explainer_is_non_scoring_and_cites_mark_scheme_point() -> None:
    repository = FakeRepository()
    result = QuestionExplainerService(
        repository,
        retriever=FakeRetriever(),
        llm=FakeLLM(),
    ).explain(
        "question-1",
        QuestionExplainRequest(mode="check_answer", student_answer="It stops at zero."),
    )

    assert result.scoring_withheld is True
    assert result.citations[0].chunk_id == "ms-1"
    assert result.citations[0].point_label == "MP1"
    assert all(citation.source_type == "mark_scheme" for citation in result.citations)
