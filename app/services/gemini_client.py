from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiClient:
    """Server-side Gemini client using Google's generateContent REST API."""

    API_URL = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )

    @classmethod
    def generate_json(cls, prompt: str) -> dict[str, Any]:
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
                    headers={"x-goog-api-key": api_key},
                    json=body,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("Gemini API request timed out")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Gemini AI request timed out",
            ) from exc
        except httpx.HTTPStatusError as exc:
            # Log only the upstream status code. Never log credentials, request
            # headers, prompts, or raw provider response bodies.
            logger.warning(
                "Gemini API returned HTTP status=%s",
                exc.response.status_code,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini AI request failed",
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Gemini API transport error type=%s",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini AI request failed",
            ) from exc
        try:
            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text.strip().strip("`"))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Gemini API returned an invalid structured response")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned an invalid structured response",
            ) from exc
        if not isinstance(result, dict):
            logger.warning("Gemini API returned a non-object JSON response")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned an invalid response shape",
            )
        return result
