"""Shared backend-only Gemini text generation for summaries and chat."""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class GeminiServiceError(RuntimeError):
    code = "gemini_request_failed"


class GeminiConfigurationError(GeminiServiceError):
    code = "gemini_not_configured"


class GeminiAuthenticationError(GeminiServiceError):
    code = "gemini_authentication_failed"


class GeminiQuotaError(GeminiServiceError):
    code = "gemini_quota_exceeded"


class GeminiModelError(GeminiServiceError):
    code = "gemini_model_unavailable"


class GeminiTimeoutError(GeminiServiceError):
    code = "gemini_timeout"


class GeminiResponseError(GeminiServiceError):
    code = "gemini_invalid_response"


def gemini_model_name() -> str:
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    if not model:
        raise GeminiConfigurationError("GEMINI_MODEL is not configured")
    return model


def _classified_error(exc: Exception) -> GeminiServiceError:
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return GeminiAuthenticationError(
            "Gemini authentication failed; check the backend GEMINI_API_KEY"
        )
    if code == 429:
        return GeminiQuotaError("Gemini quota or rate limit was reached")
    if code == 404:
        return GeminiModelError(
            "Configured Gemini model was not found or is unavailable to this project"
        )
    if code in (408, 504):
        return GeminiTimeoutError("Gemini request timed out")
    return GeminiServiceError("Gemini request failed")


def generate_text(
    prompt: str,
    *,
    system_instruction: str,
    history: list[dict] | None = None,
    temperature: float = 0.2,
) -> tuple[str, str]:
    """Generate text through Gemini without exposing credentials to callers."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is not configured on the API server"
        )

    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as exc:
        raise GeminiConfigurationError(
            "Google Gen AI SDK is not installed; install requirements-gemini.txt"
        ) from exc

    model = gemini_model_name()
    contents = []
    for message in (history or [])[-8:]:
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        role = "user" if message.get("role") == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=content)])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    )

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60_000),
    )
    try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=temperature,
                    ),
                )
                text = (getattr(response, "text", None) or "").strip()
                if not text:
                    raise GeminiResponseError("Gemini returned an empty response")
                return text, model
            except errors.APIError as exc:
                if getattr(exc, "code", None) in TRANSIENT_STATUS_CODES and attempt < 2:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise _classified_error(exc) from exc
        raise GeminiServiceError("Gemini request failed after retries")
    finally:
        client.close()
