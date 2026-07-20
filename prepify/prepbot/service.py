from __future__ import annotations

from typing import Any

import httpx

from prepify.config import Settings
from prepify.schemas import PrepBotChatRequest, PrepBotChatResponse


SYSTEM_INSTRUCTION = """You are Prep-bot, a concise tutor for Cambridge International
AS & A Level Computer Science (9618). Help students understand concepts, debug reasoning,
plan revision, and navigate Prepify. Prefer guiding questions and small examples. Never claim
that your response is an official Cambridge mark or mark scheme. Do not invent the student's
results, platform state, citations, or exam rules. If a question needs official grading, direct
the student to submit it through the relevant Prepify exam surface."""


class GeminiPrepBotService:
    def __init__(self, config: Settings, client: httpx.Client | None = None):
        self.config = config
        self.client = client

    def chat(self, request: PrepBotChatRequest) -> PrepBotChatResponse:
        if not self.config.gemini_api_key:
            raise RuntimeError("Prep-bot is not configured on the API server")
        transcript = [
            {"role": turn.role, "content": turn.text}
            for turn in request.history[-8:]
        ]
        transcript.append({"role": "user", "content": request.message})
        payload = {
            "model": self.config.gemini_model_name,
            "input": transcript,
            "system_instruction": SYSTEM_INSTRUCTION,
            "store": False,
            "generation_config": {
                "temperature": 0.25,
                "max_output_tokens": 700,
                "thinking_level": "low",
            },
        }
        endpoint = f"{self.config.gemini_api_base_url.rstrip('/')}/interactions"
        try:
            if self.client is not None:
                response = self.client.post(
                    endpoint,
                    headers={"x-goog-api-key": self.config.gemini_api_key},
                    json=payload,
                )
            else:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        endpoint,
                        headers={"x-goog-api-key": self.config.gemini_api_key},
                        json=payload,
                    )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Prep-bot could not reach Gemini; try again shortly") from exc
        answer = self._extract_answer(response.json())
        if not answer:
            raise RuntimeError("Prep-bot received an empty Gemini response")
        return PrepBotChatResponse(
            answer=answer,
            model=self.config.gemini_model_name,
            stored=False,
        )

    @staticmethod
    def _extract_answer(payload: dict[str, Any]) -> str:
        parts: list[str] = []
        for step in payload.get("steps", []):
            if step.get("type") != "model_output":
                continue
            for item in step.get("content", []):
                if item.get("type") in {"text", "output_text"} and item.get("text"):
                    parts.append(str(item["text"]))
        if not parts and isinstance(payload.get("output"), str):
            parts.append(payload["output"])
        return "\n".join(parts).strip()
