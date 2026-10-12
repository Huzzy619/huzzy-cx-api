"""Custom LiveKit STT/TTS plugins for self-hosted raw-audio endpoints.

- STT: POST raw WAV audio, receive JSON (e.g. ``{"text": "..."}``).
- TTS: POST JSON/plain text, receive raw audio bytes (e.g. WAV).

Used for Hugging Face / RunPod-style inference endpoints for languages the
LiveKit Inference catalog does not cover well (for example Yoruba/Hausa/Igbo).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import uuid
import wave
from typing import Any, cast

import httpx
from livekit.agents import stt, tts, utils
from livekit.agents._exceptions import APIConnectionError, APIStatusError
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectOptions,
    NotGivenOr,
)
from livekit.agents.utils import AudioBuffer

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 24000
DEFAULT_NUM_CHANNELS = 1


def audio_buffer_to_wav(buffer: AudioBuffer) -> bytes:
    frame = utils.merge_frames(buffer) if isinstance(buffer, list) else buffer
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(frame.num_channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame.sample_rate)
        wav_file.writeframes(bytes(frame.data))
    return wav_buffer.getvalue()


def extract_transcript(result: object, *, response_text_key: str) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        value = result.get(response_text_key)
        if value is not None:
            return str(value).strip()
    return ""


def extract_audio_bytes(
    *, content: bytes, content_type: str | None, response_audio_key: str | None
) -> bytes:
    if content_type and content_type.startswith("audio/"):
        return content
    if not content_type or "json" not in content_type:
        return content

    try:
        payload: Any = json.loads(content)
    except ValueError as exc:
        raise APIConnectionError("raw audio TTS returned invalid JSON") from exc

    if isinstance(payload, dict):
        key = response_audio_key or "audio"
        value = payload.get(key)
        if value is None and response_audio_key is None:
            for fallback_key in ("output", "waveform", "data"):
                value = payload.get(fallback_key)
                if value is not None:
                    break
        if isinstance(value, str):
            return base64.b64decode(value)
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)

    raise APIConnectionError("raw audio TTS JSON response did not contain audio data")


class RawAudioSTT(stt.STT):
    def __init__(
        self,
        *,
        endpoint_url: str,
        token: str,
        model: str,
        language: str | None = None,
        response_text_key: str = "text",
        content_type: str = "audio/wav",
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
        )
        self._endpoint_url = endpoint_url.rstrip("/")
        self._token = token
        self._model = model
        self._language = language
        self._response_text_key = response_text_key
        self._content_type = content_type
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "custom"

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        resolved_language = (
            language if language is not NOT_GIVEN else self._language or "en"
        )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": self._content_type,
        }
        try:
            response = await self._client.post(
                self._endpoint_url,
                headers=headers,
                content=audio_buffer_to_wav(buffer),
            )
        except httpx.HTTPError as exc:
            raise APIConnectionError(f"raw audio STT request failed: {exc}") from exc

        if response.status_code >= 400:
            raise APIStatusError(
                f"raw audio STT failed with status {response.status_code}",
                status_code=response.status_code,
                body=_safe_body(response),
            )

        try:
            result: Any = response.json()
        except ValueError as exc:
            raise APIConnectionError(
                "raw audio STT returned non-JSON response"
            ) from exc

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt.SpeechData(
                    language=cast(Any, resolved_language),
                    text=extract_transcript(
                        result, response_text_key=self._response_text_key
                    ),
                )
            ],
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class RawAudioTTS(tts.TTS):
    def __init__(
        self,
        *,
        endpoint_url: str,
        token: str,
        model: str,
        language: str | None = None,
        voice: str | None = None,
        request_text_key: str = "inputs",
        request_format: str = "json",
        response_audio_key: str | None = None,
        response_format: str = "wav",
        timeout: float = 30.0,
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=DEFAULT_SAMPLE_RATE,
            num_channels=DEFAULT_NUM_CHANNELS,
        )
        self._endpoint_url = endpoint_url.rstrip("/")
        self._token = token
        self._model = model
        self._language = language
        self._request_text_key = request_text_key
        self._request_format = request_format
        self._response_audio_key = response_audio_key
        self._response_format = response_format
        self._extra_payload = dict(extra_payload or {})
        if language:
            self._extra_payload.setdefault("language", language)
        if voice:
            self._extra_payload.setdefault("voice", voice)
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "custom"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return _RawAudioChunkedStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
            client=self._client,
            token=self._token,
            endpoint_url=self._endpoint_url,
            request_text_key=self._request_text_key,
            request_format=self._request_format,
            response_audio_key=self._response_audio_key,
            response_format=self._response_format,
            extra_payload=self._extra_payload,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class _RawAudioChunkedStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        tts: RawAudioTTS,
        input_text: str,
        conn_options: APIConnectOptions,
        client: httpx.AsyncClient,
        token: str,
        endpoint_url: str,
        request_text_key: str,
        request_format: str,
        response_audio_key: str | None,
        response_format: str,
        extra_payload: dict[str, Any],
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._client = client
        self._token = token
        self._endpoint_url = endpoint_url
        self._request_text_key = request_text_key
        self._request_format = request_format
        self._response_audio_key = response_audio_key
        self._response_format = response_format
        self._extra_payload = extra_payload

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            if self._request_format == "plain_text":
                headers["Content-Type"] = "text/plain"
                response = await self._client.post(
                    self._endpoint_url,
                    headers=headers,
                    content=self.input_text.encode("utf-8"),
                )
            else:
                payload = {
                    self._request_text_key: self.input_text,
                    **self._extra_payload,
                }
                response = await self._client.post(
                    self._endpoint_url, headers=headers, json=payload
                )
        except httpx.HTTPError as exc:
            raise APIConnectionError(f"raw audio TTS request failed: {exc}") from exc

        if response.status_code >= 400:
            raise APIStatusError(
                f"raw audio TTS failed with status {response.status_code}",
                status_code=response.status_code,
                body=_safe_body(response),
            )

        audio_bytes = extract_audio_bytes(
            content=response.content,
            content_type=response.headers.get("content-type"),
            response_audio_key=self._response_audio_key,
        )
        output_emitter.initialize(
            request_id=str(uuid.uuid4()),
            sample_rate=DEFAULT_SAMPLE_RATE,
            num_channels=DEFAULT_NUM_CHANNELS,
            mime_type=f"audio/{self._response_format}",
        )
        output_emitter.push(audio_bytes)
        output_emitter.flush()


def _safe_body(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return response.text
