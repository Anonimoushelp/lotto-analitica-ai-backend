from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiClient:
    """Server-side Gemini client using Google's generateContent REST API."""

    MODEL = "gemini-3.5-flash-lite"
    API_URL = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent"
    )
    REQUEST_TIMEOUT_SECONDS = 45.0
    HTTP_503_RETRIES = 1
    RETRY_BACKOFF_SECONDS = 1.0

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
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
        response = None
        for attempt in range(cls.HTTP_503_RETRIES + 1):
            try:
                with httpx.Client(timeout=cls.REQUEST_TIMEOUT_SECONDS) as client:
                    response = client.post(
                        cls.API_URL,
                        headers={"x-goog-api-key": api_key},
                        json=body,
                    )
                    response.raise_for_status()
                break
            except httpx.TimeoutException as exc:
                logger.warning("Gemini API request timed out")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Gemini AI request timed out",
                ) from exc
            except httpx.HTTPStatusError as exc:
                upstream_status = exc.response.status_code
                if (
                    upstream_status == status.HTTP_503_SERVICE_UNAVAILABLE
                    and attempt < cls.HTTP_503_RETRIES
                ):
                    logger.warning(
                        "Gemini API returned HTTP status=503; retrying once"
                    )
                    time.sleep(cls.RETRY_BACKOFF_SECONDS)
                    continue

                logger.warning(
                    "Gemini API returned HTTP status=%s",
                    upstream_status,
                )
                if upstream_status == status.HTTP_503_SERVICE_UNAVAILABLE:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Gemini AI is temporarily unavailable; retry later",
                    ) from exc
                if upstream_status == status.HTTP_429_TOO_MANY_REQUESTS:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Gemini AI rate limit reached; retry later",
                    ) from exc
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

        if response is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini AI request failed",
            )

        try:
            payload = response.json()
            candidates = payload["candidates"]
            parts = candidates[0]["content"]["parts"]
            # Gemini can return text in more than one part. Join text parts and
            # tolerate Markdown code fences without logging the generated data.
            text = "".join(
                part["text"] for part in parts
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ).strip()
            fenced = re.fullmatch(
                r"```(?:json)?\s*(.*?)\s*```", text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if fenced:
                text = fenced.group(1).strip()
            result = json.loads(text)
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
