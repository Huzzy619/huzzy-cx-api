"""Provider registry.

The adapter is selected from configuration, never from untrusted request
input. Replace ``mock`` with the actual provider slug after a capability proof
of concept.
"""

from __future__ import annotations

from django.conf import settings

from apps.telephony.ports import TelephonyAdapter


def get_telephony_adapter() -> TelephonyAdapter:
    provider = settings.TELEPHONY_PROVIDER
    if provider == "mock":
        from apps.telephony.providers.mock import (  # noqa: PLC0415
            MockTelephonyAdapter,
        )

        return MockTelephonyAdapter.from_settings()
    raise RuntimeError(f"Unsupported TELEPHONY_PROVIDER: {provider!r}")
