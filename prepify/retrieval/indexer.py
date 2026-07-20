from __future__ import annotations

from collections import defaultdict

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from prepify.config import Settings, settings
from prepify.storage.models import Document, IngestionBlock


class QdrantIndexer:
    def __init__(self, config: Settings = settings):
        self.config = config
        self.client = (
            QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key or None)
            if config.qdrant_url
            else QdrantClient(path=config.qdrant_storage_path)
        )
        from sentence_transformers import SentenceTransformer

        self.embedding_model = SentenceTransformer(config.embedding_model_name)
        self._ensure_collections()

    def _ensure_collections(self) -> None:
        existing = {item.name for item in self.client.get_collections().collections}
        for name in (
            self.config.question_collection,
            self.config.mark_scheme_collection,
        ):
            if name not in existing:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=self.config.embedding_dim,
                        distance=Distance.COSINE,
                    ),
                )

    def _collection_for(self, block: IngestionBlock) -> str:
        if block.block_type == "mark_scheme":
            return self.config.mark_scheme_collection
        return self.config.question_collection

    def index(self, rows: list[tuple[IngestionBlock, Document]]) -> list[str]:
        grouped: dict[str, list[tuple[IngestionBlock, Document]]] = defaultdict(list)
        for block, document in rows:
            if block.review_status not in {"auto_trusted", "approved"}:
                continue
            grouped[self._collection_for(block)].append((block, document))

        indexed: list[str] = []
        for collection, items in grouped.items():
            vectors = self.embedding_model.encode(
                [block.raw_text for block, _ in items],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            points = []
            for vector, (block, document) in zip(vectors, items, strict=True):
                points.append(
                    PointStruct(
                        id=block.id,
                        vector=vector.tolist(),
                        payload={
                            "text": block.raw_text,
                            "chunk_id": block.id,
                            "document_id": document.id,
                            "source_type": block.block_type,
                            "question_id": block.question_id,
                            "question_number": block.question_number,
                            "paper_code": document.paper_code,
                            "paper_number": document.paper_number,
                            "series": document.series,
                            "topic_tag": block.topic_tag,
                            "page_number": block.page_number,
                            "point_label": block.point_label,
                            "review_status": block.review_status,
                        },
                    )
                )
                indexed.append(block.id)
            self.client.upsert(collection_name=collection, points=points, wait=True)
        return indexed
