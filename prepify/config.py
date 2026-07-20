from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://prepify:prepify@localhost:5432/prepify",
    )
    qdrant_url: str = os.getenv("QDRANT_URL", "")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
    qdrant_storage_path: str = os.getenv(
        "QDRANT_STORAGE_PATH", str(PROJECT_ROOT / "qdrant_storage")
    )

    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    embedding_dim: int = _int("EMBEDDING_DIM", 1024)
    reranker_model_name: str = os.getenv(
        "RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    top_k_retrieval: int = _int("TOP_K_RETRIEVAL", 12)
    top_k_rerank: int = _int("TOP_K_RERANK", 6)
    relevance_threshold: float = _float("RELEVANCE_THRESHOLD", 0.35)

    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv(
        "LLM_BASE_URL", "https://api.groq.com/openai/v1"
    )
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "llama-3.1-8b-instant")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_api_base_url: str = os.getenv(
        "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1"
    )
    gemini_model_name: str = os.getenv("GEMINI_MODEL_NAME", "gemini-3.5-flash")
    cors_allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    )

    ocr_api_key: str = os.getenv("OCR_API_KEY", "")
    ocr_base_url: str = os.getenv("OCR_BASE_URL", "")
    ocr_model_name: str = os.getenv("OCR_MODEL_NAME", "Qwen3-VL-8B-Instruct")
    scanned_page_min_chars: int = _int("SCANNED_PAGE_MIN_CHARS", 80)
    ocr_render_dpi: int = _int("OCR_RENDER_DPI", 180)

    docker_executable: str = os.getenv("DOCKER_EXECUTABLE", "docker")
    paper4_python_image: str = os.getenv("PAPER4_PYTHON_IMAGE", "python:3.11-alpine")
    paper4_java_image: str = os.getenv(
        "PAPER4_JAVA_IMAGE", "eclipse-temurin:21-jdk-alpine"
    )
    paper4_vb_image: str = os.getenv(
        "PAPER4_VB_IMAGE", "mcr.microsoft.com/dotnet/sdk:8.0-alpine"
    )
    sandbox_timeout_seconds: int = _int("SANDBOX_TIMEOUT_SECONDS", 5)
    sandbox_memory_mb: int = _int("SANDBOX_MEMORY_MB", 256)
    sandbox_cpus: float = _float("SANDBOX_CPUS", 0.5)
    sandbox_pids_limit: int = _int("SANDBOX_PIDS_LIMIT", 64)
    sandbox_max_output_bytes: int = _int("SANDBOX_MAX_OUTPUT_BYTES", 65_536)
    sandbox_max_resource_bytes: int = _int("SANDBOX_MAX_RESOURCE_BYTES", 10 * 1024 * 1024)
    sandbox_workspace_root: str = os.getenv(
        "SANDBOX_WORKSPACE_ROOT", str(PROJECT_ROOT / ".sandbox")
    )
    phase1_resource_root: str = os.getenv(
        "PHASE1_RESOURCE_ROOT", str(PROJECT_ROOT / "data" / "phase1_resources")
    )
    phase1_validation_min_submissions: int = _int(
        "PHASE1_VALIDATION_MIN_SUBMISSIONS", 20
    )

    question_collection: str = "prepify_question_text"
    mark_scheme_collection: str = "prepify_mark_scheme"


settings = Settings()
