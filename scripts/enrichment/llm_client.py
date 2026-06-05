from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod

import requests


class LLMClient(ABC):
    @abstractmethod
    def generate_json(self, system: str, user: str, *, schema_name: str) -> dict:
        ...


class MockLLMClient(LLMClient):
    """Returns minimal valid stubs — useful for pipeline testing without a real LLM."""

    def generate_json(self, system: str, user: str, *, schema_name: str) -> dict:
        if schema_name == "article_summary":
            return {
                "summary": "Resumo gerado pelo mock.",
                "whatHappened": "Evento genérico.",
                "mainClaims": ["Afirmação mock."],
                "keyEntities": [],
                "datesAndNumbers": [],
                "articleType": "news",
                "tone": "neutral",
                "notableFraming": "",
                "limitations": ["Mock sem leitura real do texto."],
                "confidence": "low",
            }
        if schema_name == "cluster_summary":
            return {
                "neutralHeadline": "Título neutro mock",
                "neutralSummary": "Resumo consolidado mock.",
                "whatHappened": "Evento central mock.",
                "whyItMatters": "Importância mock.",
                "knownFacts": [],
                "reportedClaims": [],
                "coverageDifferences": [],
                "headlineDivergence": {"level": "low", "explanation": "Sem divergência detectada."},
                "openQuestions": [],
                "newsletterBlurb": "Blurb mock.",
                "confidence": "low",
            }
        return {}


def _extract_json(text: str) -> dict:
    """Try to parse JSON from LLM output, handling markdown code fences."""
    text = text.strip()
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Find first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


class OllamaClient(LLMClient):
    """Client for a local Ollama instance."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
        max_retries: int = 2,
    ) -> None:
        self.model = model or os.environ.get("LOCAL_LLM_MODEL", "llama3.2:3b")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def _call(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "prompt": f"{system}\n\n{user}",
            "stream": False,
            "format": "json",
        }
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def generate_json(self, system: str, user: str, *, schema_name: str) -> dict:
        last_err: Exception | None = None
        raw = ""
        for attempt in range(self.max_retries + 1):
            try:
                if attempt == 0:
                    raw = self._call(system, user)
                else:
                    retry_prompt = (
                        f"Your previous response was not valid JSON. "
                        f"Raw output:\n{raw}\n\n"
                        f"Return ONLY valid JSON, no markdown, no explanation."
                    )
                    raw = self._call(system, retry_prompt)
                return _extract_json(raw)
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                last_err = e
        raise ValueError(f"LLM returned invalid JSON after {self.max_retries + 1} attempts: {last_err}\nRaw: {raw[:500]}")


def make_client(model: str | None = None, mock: bool = False) -> LLMClient:
    if mock:
        return MockLLMClient()
    return OllamaClient(model=model)
