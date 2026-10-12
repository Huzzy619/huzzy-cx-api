"""Defaults and shared constants for worker-side builders."""

from __future__ import annotations

DEFAULT_INSTRUCTIONS = (
    "You are Kora CX, a helpful and concise voice assistant. "
    "Never invent account, transaction, or policy information."
)
DEFAULT_LLM = "openai/gpt-4o-mini"
DEFAULT_LLM_FALLBACK = "google/gemini-2.5-flash"
DEFAULT_STT_MODEL = "deepgram/nova-3:en"
DEFAULT_TTS_MODEL = "cartesia/sonic-3"
DEFAULT_TTS_VOICE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"

# Tool ids shared with the platform allow-list.
TOOL_KNOWLEDGE = "search_approved_knowledge"
TOOL_TRANSACTION_STATUS = "get_transaction_status"
TOOL_GET_SUPPORT_CASE = "get_support_case"
TOOL_CREATE_SUPPORT_CASE = "create_support_case"
TOOL_HANDOFF = "request_human_handoff"
TOOL_END_INTERACTION = "end_interaction"

# LiveKit BuiltinAudioClip names -> worker constant names.
AMBIENT_SOUND_CLIPS = ("keyboard_typing", "keyboard_typing2", "office", "crowd")
