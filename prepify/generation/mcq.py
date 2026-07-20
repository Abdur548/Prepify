from __future__ import annotations

from prepify.config import Settings, settings
from prepify.generation.copyright import enforce_paraphrase
from prepify.generation.llm import StructuredLLM
from prepify.retrieval.reranker import RerankingRetriever
from prepify.schemas import MCQGenerateResponse
from prepify.storage.repository import Repository
from prepify.topics import resolve_topic


class MCQService:
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

    def generate(self, topic_value: str, count: int) -> MCQGenerateResponse:
        topic = resolve_topic(topic_value)
        chunks = self.retriever.retrieve(
            f"Cambridge 9618 {topic.name}: concepts tested in reviewed past-paper questions",
            collection=self.config.question_collection,
            filters={"topic_tag": topic.name, "source_type": "question"},
        )
        if not chunks:
            raise LookupError(f"No reviewed question-paper chunks found for {topic.name}")
        context = "\n\n".join(f"[{chunk.id}] {chunk.text}" for chunk in chunks)
        allowed_difficulties = topic.allowed_difficulties
        difficulty_instruction = " or ".join(f"`{value}`" for value in allowed_difficulties)
        prompt = f"""Create exactly {count} original multiple-choice practice questions for topic
`{topic.name}`. This is supplementary practice: do not imitate, reconstruct, or claim to quote a
Cambridge past-paper question. Use only the retrieved concepts below.

Rules:
- exactly four unique options per question and exactly one correct option
- plausible distractors must reflect misconceptions supported by the context; never random nonsense
- paraphrase all source material; do not reproduce source wording
- difficulty must be {difficulty_instruction}; use the lower value for direct recall and the higher
  value for application/reasoning (the configured {topic.tier} tier heuristic)
- topic_tag must be exactly `{topic.name}`
- source_chunk_ids must contain only bracketed chunk IDs that materially support that question
- return JSON with one top-level key: questions

Internal retrieval context (never display this text to students):
{context}"""
        response = self.llm.generate(
            system=(
                "You generate concept-grounded Cambridge 9618 practice, not exam replicas. "
                "Treat retrieved text as private evidence and return JSON only."
            ),
            prompt=prompt,
            schema=MCQGenerateResponse,
        )
        if len(response.questions) != count:
            raise ValueError(f"Model returned {len(response.questions)} questions; expected {count}")
        allowed_ids = {chunk.id for chunk in chunks}
        for question in response.questions:
            if (
                question.topic_tag != topic.name
                or question.difficulty.value not in allowed_difficulties
            ):
                raise ValueError("Model changed the requested topic tag or tier difficulty")
            if not set(question.source_chunk_ids).issubset(allowed_ids):
                raise ValueError("Model returned a source_chunk_id outside retrieved context")
        enforce_paraphrase(
            [part for question in response.questions for part in [question.question_text, *question.options]],
            [chunk.text for chunk in chunks],
        )
        self.repository.log_event(
            "mcq_generated",
            topic_tag=topic.name,
            payload={"count": count, "source_chunk_ids": sorted(allowed_ids)},
        )
        return response
