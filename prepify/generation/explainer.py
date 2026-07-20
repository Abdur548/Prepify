from __future__ import annotations

from pydantic import BaseModel, Field

from prepify.config import Settings, settings
from prepify.generation.copyright import enforce_paraphrase
from prepify.generation.llm import StructuredLLM
from prepify.retrieval.reranker import RerankingRetriever
from prepify.retrieval.retriever import RetrievedChunk
from prepify.schemas import (
    ExplainMode,
    InternalCitation,
    QuestionExplainRequest,
    QuestionExplainResponse,
)
from prepify.storage.repository import Repository


class _ExplanationDraft(BaseModel):
    explanation: str = Field(min_length=1)
    reasoning_steps: list[str] = Field(min_length=1)
    answer_feedback: str | None = None


def _context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{chunk.id} | {chunk.payload.get('source_type')} | point={chunk.payload.get('point_label')}] "
        f"{chunk.text}"
        for chunk in chunks
    )


def _citation(chunk: RetrievedChunk) -> InternalCitation:
    payload = chunk.payload
    return InternalCitation(
        chunk_id=chunk.id,
        source_type=payload.get("source_type", "question"),
        document_id=str(payload.get("document_id")),
        question_id=payload.get("question_id"),
        page_number=payload.get("page_number"),
        point_label=payload.get("point_label"),
    )


class QuestionExplainerService:
    def __init__(
        self,
        repository: Repository,
        *,
        retriever: RerankingRetriever | None = None,
        llm: StructuredLLM | None = None,
        config: Settings = settings,
    ):
        self.repository = repository
        self.config = config
        self.retriever = retriever or RerankingRetriever(config)
        self.llm = llm or StructuredLLM(config)

    def explain(
        self,
        question_id: str,
        request: QuestionExplainRequest,
    ) -> QuestionExplainResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise KeyError(question_id)
        if not question.linked_mark_scheme_id:
            raise LookupError("Question has no linked mark scheme document")

        query = f"Explain the reasoning and mark-scheme requirements for question {question.question_number}"
        question_chunks = self.retriever.retrieve(
            query,
            collection=self.config.question_collection,
            filters={"question_id": question_id, "source_type": "question"},
            top_k=4,
        )
        mark_chunks = self.retriever.retrieve(
            query,
            collection=self.config.mark_scheme_collection,
            filters={"question_id": question_id, "source_type": "mark_scheme"},
            top_k=6,
        )
        if not question_chunks:
            raise LookupError("No reviewed question context found")
        if not mark_chunks:
            raise LookupError("No reviewed mark-scheme points found")
        question_context = question_chunks
        all_chunks = question_chunks + mark_chunks
        student_section = (
            f"\nStudent answer to discuss:\n{request.student_answer}"
            if request.student_answer
            else ""
        )
        mode_instruction = {
            ExplainMode.explain: "Explain what the question is asking and how to approach it.",
            ExplainMode.reasoning: "Give a step-by-step reasoning path. For pseudocode/code, trace the algorithm logic step by step.",
            ExplainMode.check_answer: (
                "Compare the student's answer with the evidence. Describe correct ideas, missing ideas, and misconceptions."
            ),
        }[request.mode]
        prompt = f"""{mode_instruction}

This is formative explanation only. Never award marks, calculate a score or percentage, predict a
grade, or use grading language. Paraphrase the question and mark scheme; do not reproduce them.
Tie the explanation to the specific mark-scheme points in the private context. Do not expose raw
context or bracketed internal identifiers in prose. Return JSON with explanation, reasoning_steps,
and answer_feedback (null unless a student answer was supplied).
{student_section}

Private question context:
{_context(question_context)}

Private linked mark-scheme context:
{_context(mark_chunks)}"""
        draft = self.llm.generate(
            system=(
                "You are a retrieval-grounded Cambridge 9618 tutor. You explain but never grade. "
                "Retrieved copyrighted text is private evidence and must be paraphrased."
            ),
            prompt=prompt,
            schema=_ExplanationDraft,
        )
        generated_parts = [draft.explanation, *draft.reasoning_steps]
        if draft.answer_feedback:
            generated_parts.append(draft.answer_feedback)
        enforce_paraphrase(generated_parts, [chunk.text for chunk in all_chunks])
        citations = [_citation(chunk) for chunk in mark_chunks]
        self.repository.log_event(
            "question_explained",
            question_id=question_id,
            topic_tag=question.topic_tag,
            payload={
                "mode": request.mode.value,
                "source_chunk_ids": [chunk.id for chunk in all_chunks],
                "student_answer_supplied": bool(request.student_answer),
            },
        )
        return QuestionExplainResponse(
            question_id=question_id,
            explanation=draft.explanation,
            reasoning_steps=draft.reasoning_steps,
            answer_feedback=draft.answer_feedback,
            scoring_withheld=True,
            citations=citations,
        )
