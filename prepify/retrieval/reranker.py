from __future__ import annotations

from prepify.config import Settings, settings
from prepify.retrieval.retriever import FilteredRetriever, RetrievedChunk


class RerankingRetriever:
    """Dense retrieval followed by ms-marco-MiniLM-L-6-v2 reranking."""

    def __init__(
        self,
        config: Settings = settings,
        retriever: FilteredRetriever | None = None,
    ):
        self.config = config
        self.retriever = retriever or FilteredRetriever(config)
        from sentence_transformers import CrossEncoder

        self.reranker = CrossEncoder(config.reranker_model_name)

    def retrieve(
        self,
        query: str,
        *,
        collection: str,
        filters: dict | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        candidates = self.retriever.retrieve(
            query,
            collection=collection,
            filters=filters,
            top_k=self.config.top_k_retrieval,
        )
        if not candidates:
            return []
        scores = self.reranker.predict([(query, chunk.text) for chunk in candidates])
        reranked = [
            RetrievedChunk(chunk.id, chunk.text, float(score), chunk.payload)
            for chunk, score in zip(candidates, scores, strict=True)
        ]
        reranked.sort(key=lambda chunk: chunk.score, reverse=True)
        return reranked[: (top_k or self.config.top_k_rerank)]

