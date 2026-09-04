from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import settings


class GeminiService:
    """Thin, server-side client for Google's Gemini REST API."""

    API_URL = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned an invalid structured response",
            ) from exc
        if not isinstance(value, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned an invalid response shape",
            )
        return value

    @classmethod
    def generate(cls, prompt: str) -> dict[str, Any]:
        api_key = getattr(settings, "gemini_api_key", "")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini AI is not configured",
            )

        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    cls.API_URL,
                    params={"key": api_key},
                    json=body,
                )
                response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini AI request failed",
            ) from exc

        try:
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned no usable content",
            ) from exc
        return cls._extract_json(text)
