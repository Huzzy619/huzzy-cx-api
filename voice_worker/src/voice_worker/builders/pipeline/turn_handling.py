"""Turn detection and interruption tuning builder."""

from __future__ import annotations

from livekit.agents import TurnHandlingOptions
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from voice_worker.builders.utils import scale_to_range
from voice_worker.schemas import AgentConfig


class TurnHandlingBuilder:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def build(self) -> TurnHandlingOptions:
        speech = self._config.speech_config
        if not speech:
            return TurnHandlingOptions(turn_detection=MultilingualModel())

        min_delay = scale_to_range(speech.responsiveness, high=1.0, low=0.2)
        max_delay = max(min_delay + 0.5, 3.0)
        min_duration = scale_to_range(
            speech.interruption_sensitivity, high=0.8, low=0.2
        )
        return TurnHandlingOptions(
            turn_detection=MultilingualModel(),
            endpointing={
                "mode": "fixed",
                "min_delay": min_delay,
                "max_delay": max_delay,
            },
            interruption={
                "mode": "adaptive",
                "min_duration": min_duration,
                "min_words": 0,
            },
        )
