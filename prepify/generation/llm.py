from __future__ import annotations

import json
import re
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from prepify.config import Settings, settings


T = TypeVar("T", bound=BaseModel)


class StructuredLLM:
    def __init__(self, config: Settings = settings):
        if not config.llm_api_key:
            raise RuntimeError("LLM_API_KEY is required for generation endpoints")
        self.config = config
        self.client = OpenAI(api_key=config.llm_api_key, base_url=config.llm_base_url)

    def generate(self, *, system: str, prompt: str, schema: type[T]) -> T:
        response = self.client.chat.completions.create(
            model=self.config.llm_model_name,
            temperature=0.25,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        return schema.model_validate(parsed)

