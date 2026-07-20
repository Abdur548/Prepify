from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from prepify import __version__
from prepify.assembly.schemas import (
    AssembleExamRequest,
    AssembledExamResponse,
    MCQAnswerRequest,
    MCQAnswerResponse,
)
from prepify.assembly.service import ExamAssembler
from prepify.config import settings
from prepify.generation.explainer import QuestionExplainerService
from prepify.generation.mcq import MCQService
from prepify.phase1.grader import Paper4CodeExecutionGrader
from prepify.phase1.repository import Paper4Repository
from prepify.phase1.sandbox import DockerSandbox
from prepify.phase1.schemas import Paper4GradeRequest, Paper4GradeResponse
from prepify.prepbot.service import GeminiPrepBotService
from prepify.schemas import (
    MCQGenerateRequest,
    MCQGenerateResponse,
    PrepBotChatRequest,
    PrepBotChatResponse,
    QuestionExplainRequest,
    QuestionExplainResponse,
)
from prepify.storage.database import SessionLocal
from prepify.storage.repository import Repository
from prepify.topics import TOPICS, resolve_topic


app = FastAPI(
    title="Prepify 9618 MVP1–MVP3 API",
    version=__version__,
    description=(
        "Practice, explanations, provisional Paper 4 execution grading, and validated-content "
        "exam assembly. Missing MVP2 phases remain explicitly gated."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def build_mcq_service(session: Session) -> MCQService:
    return MCQService(Repository(session))


def build_explainer_service(session: Session) -> QuestionExplainerService:
    return QuestionExplainerService(Repository(session))


def build_paper4_grader(session: Session) -> Paper4CodeExecutionGrader:
    return Paper4CodeExecutionGrader(Paper4Repository(session))


def build_exam_assembler(session: Session) -> ExamAssembler:
    return ExamAssembler(session)


def build_prep_bot_service() -> GeminiPrepBotService:
    return GeminiPrepBotService(settings)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "prepify-9618", "version": __version__}


@app.get("/v1/topics")
def topics() -> list[dict]:
    return [
        {"code": topic.code, "topic_tag": topic.name, "tier": topic.tier}
        for topic in TOPICS
    ]


@app.post("/v1/mcq/generate", response_model=MCQGenerateResponse)
def generate_mcqs(
    request: MCQGenerateRequest,
    session: Session = Depends(get_session),
) -> MCQGenerateResponse:
    try:
        resolve_topic(request.topic_tag)
        return build_mcq_service(session).generate(request.topic_tag, request.count)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/v1/questions/{question_id}/explain",
    response_model=QuestionExplainResponse,
)
def explain_question(
    question_id: str,
    request: QuestionExplainRequest,
    session: Session = Depends(get_session),
) -> QuestionExplainResponse:
    try:
        return build_explainer_service(session).explain(question_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Question not found") from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post(
    "/v1/phase1/questions/{question_id}/grade-code",
    response_model=Paper4GradeResponse,
)
def grade_paper4_code(
    question_id: str,
    request: Paper4GradeRequest,
    session: Session = Depends(get_session),
) -> Paper4GradeResponse:
    try:
        return build_paper4_grader(session).grade(question_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Question not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/capabilities")
def capabilities(session: Session = Depends(get_session)) -> dict:
    paper4_status = Paper4Repository(session).validation_status(
        sandbox_profile=DockerSandbox().profile
    )
    return {
        "paper4_execution": {
            "available": True,
            "validation_status": paper4_status,
            "certified": paper4_status == "validated",
        },
        "paper2_pseudocode": {
            "available": False,
            "status": "gated_not_implemented",
            "reason": "MVP2 Phase 2 cannot start until Phase 1 real-submission validation passes.",
        },
        "paper1_3_written": {
            "available": False,
            "status": "gated_not_implemented",
            "reason": "MVP2 Phase 3 depends on the unbuilt and unvalidated Phase 2.",
        },
        "prep_bot": {
            "available": bool(settings.gemini_api_key),
            "model": settings.gemini_model_name,
            "stored": False,
        },
    }


@app.post("/v1/prep-bot/chat", response_model=PrepBotChatResponse)
def chat_with_prep_bot(request: PrepBotChatRequest) -> PrepBotChatResponse:
    try:
        return build_prep_bot_service().chat(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/v1/exams/assemble", response_model=AssembledExamResponse)
def assemble_exam(
    request: AssembleExamRequest,
    session: Session = Depends(get_session),
) -> AssembledExamResponse:
    try:
        return build_exam_assembler(session).assemble(request)
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/exams/{assembly_id}", response_model=AssembledExamResponse)
def get_assembled_exam(
    assembly_id: str,
    session: Session = Depends(get_session),
) -> AssembledExamResponse:
    try:
        return build_exam_assembler(session).get(assembly_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Assembled exam not found") from exc


@app.post(
    "/v1/exams/{assembly_id}/questions/{item_id}/answer-mcq",
    response_model=MCQAnswerResponse,
)
def answer_assembled_mcq(
    assembly_id: str,
    item_id: str,
    request: MCQAnswerRequest,
    session: Session = Depends(get_session),
) -> MCQAnswerResponse:
    try:
        return build_exam_assembler(session).grade_mcq(
            assembly_id, item_id, request.selected_option_index
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Assembly question not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
