from __future__ import annotations

from urllib.parse import urljoin

import httpx

from app.core.config import Settings


class GradiumError(RuntimeError):
    pass


class GradiumClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def stt_url(self) -> str:
        return urljoin(
            self.settings.gradium_base_url.rstrip("/") + "/",
            self.settings.gradium_stt_path.lstrip("/"),
        )

    async def transcribe(
        self, data: bytes, content_type: str, *, language: str | None = None
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.settings.gradium_api_key}",
            "x-api-key": self.settings.gradium_api_key,
        }
        files = {"file": ("site-call.webm", data, content_type or "audio/webm")}
        form_data = {}
        if language:
            form_data["language"] = language
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.gradium_timeout_seconds
            ) as client:
                response = await client.post(
                    self.stt_url,
                    headers=headers,
                    files=files,
                    data=form_data or None,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GradiumError(
                f"Gradium STT returned {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise GradiumError("Gradium STT request failed.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GradiumError("Gradium STT returned a non-JSON response.") from exc

        transcript = _find_transcript(payload)
        if not transcript:
            raise GradiumError("Gradium STT response did not include a transcript.")
        return transcript


def _find_transcript(payload: object) -> str | None:
    if isinstance(payload, str):
        return payload.strip() or None
    if isinstance(payload, list):
        for item in payload:
            found = _find_transcript(item)
            if found:
                return found
        return None
    if not isinstance(payload, dict):
        return None

    for key in ("transcript", "text", "transcription"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("result", "data", "output"):
        found = _find_transcript(payload.get(key))
        if found:
            return found
    return None
