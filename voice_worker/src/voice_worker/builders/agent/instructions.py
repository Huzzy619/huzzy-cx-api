"""System prompt and instruction augmentation from voice-agent config."""

from __future__ import annotations

from voice_worker.builders.utils import resolve_language
from voice_worker.constants import DEFAULT_INSTRUCTIONS
from voice_worker.schemas import AgentConfig


class InstructionsBuilder:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def build(self) -> str:
        instructions = self._config.system_prompt or DEFAULT_INSTRUCTIONS

        language = resolve_language(self._config)
        if language:
            instructions += (
                f"\n\nSpeak with the caller in the appropriate language for {language}."
            )

        escalation_text = self._build_escalation_instructions()
        if escalation_text:
            instructions = f"{instructions}\n\n{escalation_text}"

        security = self._config.call_security_config
        if security and security.sensitive_data_masking:
            instructions += (
                "\n\nNever repeat or log sensitive data such as full payment card "
                "numbers, passwords, PINs, or government IDs."
            )
        return instructions

    def _build_escalation_instructions(self) -> str:
        escalation = self._config.escalation_config
        if not escalation or not escalation.enable_escalation:
            return ""

        lines = [
            "Escalation is enabled. Offer to transfer to a human when appropriate."
        ]
        if escalation.handoff_message:
            lines.append(f"Handoff message: {escalation.handoff_message}")
        conditions = escalation.trigger_conditions
        if conditions:
            triggers = []
            if conditions.customer_asks_for_human:
                triggers.append("the customer asks for a human")
            if conditions.anger_or_frustration_detected:
                triggers.append("anger or frustration is detected")
            if conditions.query_is_beyond_agent_scope:
                triggers.append("the query is beyond your scope")
            if conditions.payment_dispute_raised:
                triggers.append("a payment dispute is raised")
            if conditions.legal_compliance_topic:
                triggers.append("legal or compliance topics arise")
            if triggers:
                lines.append("Escalate when: " + "; ".join(triggers) + ".")
        return "\n".join(lines)
