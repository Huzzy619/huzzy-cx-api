"""Room I/O options builder (noise cancellation)."""

from __future__ import annotations

from typing import Any

from livekit.agents import room_io
from livekit.plugins import noise_cancellation

from voice_worker.schemas import AgentConfig


class RoomOptionsBuilder:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def build(self) -> room_io.RoomOptions:
        use_noise_cancellation = True
        transcription = self._config.transcription_config
        if transcription:
            use_noise_cancellation = transcription.background_noise_denoising

        kwargs: dict[str, Any] = {}
        if use_noise_cancellation:
            kwargs["audio_input"] = room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            )
        return room_io.RoomOptions(**kwargs)
