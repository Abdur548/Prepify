from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from prepify.config import Settings, settings


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    text: str
    score: float
    payload: dict[str, Any]


class FilteredRetriever:
    """BAAI/bge-m3 retrieval with metadata filters required by MVP1."""

    def __init__(self, config: Settings = settings):
        self.config = config
        self.client = (
            QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key or None)
            if config.qdrant_url
            else QdrantClient(path=config.qdrant_storage_path)
        )
        from sentence_transformers import SentenceTransformer

        self.embedding_model = SentenceTransformer(config.embedding_model_name)

    @staticmethod
    def _filter(values: dict[str, Any] | None) -> Filter:
        conditions = [FieldCondition(key="review_status", match=MatchAny(any=["auto_trusted", "approved"]))]
        for key, value in (values or {}).items():
            if value is None:
                continue
            match = MatchAny(any=value) if isinstance(value, (list, tuple, set)) else MatchValue(value=value)
            conditions.append(FieldCondition(key=key, match=match))
        return Filter(must=conditions)

    def retrieve(
        self,
        query: str,
        *,
        collection: str,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        vector = self.embedding_model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0]
        limit = top_k or self.config.top_k_retrieval
        query_filter = self._filter(filters)
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=collection,
                query=vector.tolist(),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            points = response.points
        else:  # qdrant-client compatibility with the reused course_rag_v2 stack
            points = self.client.search(
                collection_name=collection,
                query_vector=vector.tolist(),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
        return [
            RetrievedChunk(
                id=str(point.id),
                text=str((point.payload or {}).get("text", "")),
                score=float(point.score),
                payload=dict(point.payload or {}),
            )
            for point in points
        ]

