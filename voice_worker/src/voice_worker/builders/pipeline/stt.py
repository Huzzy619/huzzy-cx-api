"""Speech-to-text pipeline builder with fallback and optional diarization."""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import inference, stt, vad

from voice_worker.builders.pipeline.custom_providers import resolve_custom_stt
from voice_worker.constants import DEFAULT_STT_MODEL
from voice_worker.schemas import AgentConfig

logger = logging.getLogger(__name__)

_DIARIZATION_EXTRA_KWARGS: dict[str, dict[str, Any]] = {
    "deepgram": {"diarize": True},
    "assemblyai": {"speaker_labels": True},
    "speechmatics": {"diarization": "speaker"},
    "xai": {"diarize": True},
}


def _provider_from_model(model: str) -> str:
    return model.split("/")[0].lower()


def _create_inference_stt(
    model: str, *, enable_diarization: bool, language: str | None
) -> stt.STT:
    if language:
        model = f"{model}:{language}"

    extra_kwargs = (
        _DIARIZATION_EXTRA_KWARGS.get(_provider_from_model(model))
        if enable_diarization
        else None
    )
    if enable_diarization and extra_kwargs is None:
        logger.warning(
            "Speaker diarization requested but STT model %s does not support it",
            model,
        )
        return inference.STT.from_model_string(model)
    if extra_kwargs:
        return inference.STT(model=model, extra_kwargs=extra_kwargs)
    return inference.STT.from_model_string(model)


class STTBuilder:
    def __init__(self, config: AgentConfig, *, vad_instance: vad.VAD | None = None):
        self._config = config
        self._vad = vad_instance

    @property
    def _diarization_enabled(self) -> bool:
        transcription = self._config.transcription_config
        return bool(transcription and transcription.speaker_diarization)

    def build(self) -> stt.STT:
        transcription = self._config.transcription_config
        diarization = self._diarization_enabled
        language = self._config.language or None

        base: stt.STT | None = None
        if transcription and transcription.stt_model:
            base = resolve_custom_stt(transcription.stt_model, language=language)
            if base is None:
                base = _create_inference_stt(
                    transcription.stt_model,
                    enable_diarization=diarization,
                    language=language,
                )
        if base is None:
            base = _create_inference_stt(
                DEFAULT_STT_MODEL, enable_diarization=diarization, language=language
            )

        if not diarization:
            return base
        if not base.capabilities.diarization:
            logger.warning(
                "Diarization requested but configured STT does not report support"
            )
            return base
        return stt.MultiSpeakerAdapter(
            stt=base,
            detect_primary_speaker=True,
            suppress_background_speaker=True,
            primary_format="{text}",
            background_format="[Speaker {speaker_id}] {text}",
        )
