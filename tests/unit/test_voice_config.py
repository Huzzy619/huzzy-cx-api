"""Unit tests for voice-agent configuration validation."""

from __future__ import annotations

import pytest

from apps.voice_agents.schemas import VoiceAgentConfig

pytestmark = pytest.mark.unit


def test_valid_config_parses():
    config = VoiceAgentConfig.model_validate(
        {
            "greeting": "Hello",
            "model": "gpt-x",
            "tools": ["search_approved_knowledge"],
        }
    )
    config.validate_tools()
    assert config.language == "en-NG"
    assert config.max_call_seconds == 600


def test_unknown_tool_is_rejected():
    config = VoiceAgentConfig.model_validate(
        {"greeting": "Hi", "model": "m", "tools": ["drop_database"]}
    )
    with pytest.raises(ValueError, match="Unsupported tools"):
        config.validate_tools()


def test_extra_fields_are_forbidden():
    with pytest.raises(ValueError):
        VoiceAgentConfig.model_validate(
            {"greeting": "Hi", "model": "m", "api_key": "secret"}
        )


def test_temperature_bounds():
    with pytest.raises(ValueError):
        VoiceAgentConfig.model_validate(
            {"greeting": "Hi", "model": "m", "temperature": 5.0}
        )


def test_nested_pipeline_config_parses():
    config = VoiceAgentConfig.model_validate(
        {
            "greeting": "Hello",
            "model": "m",
            "tools": ["search_approved_knowledge"],
            "voice": "ash",
            "transcription_config": {
                "stt_model": "deepgram/nova-3",
                "tts_model": "cartesia/sonic-3",
                "speaker_diarization": True,
            },
            "speech_config": {
                "responsiveness": 7,
                "ambient_sound": "keyboard_typing",
            },
            "call_config": {
                "voice_mail_detection": True,
                "media_encryption": "DTLS_SRTP",
            },
            "escalation_config": {
                "enable_escalation": True,
                "call_transfer_number": "+2348000000000",
                "trigger_conditions": {"customer_asks_for_human": True},
            },
            "recording_disclosure": "This call is recorded.",
            "read_recording_disclosure": True,
        }
    )
    config.validate_tools()
    assert config.transcription_config.speaker_diarization is True
    assert config.escalation_config.trigger_conditions.customer_asks_for_human
    assert config.call_config.media_encryption == "DTLS_SRTP"


def test_nested_config_rejects_unknown_fields():
    with pytest.raises(ValueError):
        VoiceAgentConfig.model_validate(
            {"greeting": "Hi", "model": "m", "speech_config": {"bogus": 1}}
        )


def test_speech_config_bounds():
    with pytest.raises(ValueError):
        VoiceAgentConfig.model_validate(
            {"greeting": "Hi", "model": "m", "speech_config": {"responsiveness": 11}}
        )
