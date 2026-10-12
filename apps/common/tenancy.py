"""Helpers for enforcing tenant boundaries.

Django foreign keys do not guarantee that two related rows belong to the same
organisation. Every service that links tenant-scoped records must call one of
these helpers so a cross-tenant reference is rejected before it is persisted.
"""

from __future__ import annotations

from collections.abc import Iterable

from apps.common.exceptions import TenantIsolationError


def assert_same_organisation(
    *, organisation, objects: Iterable[tuple[str, object]]
) -> None:
    """Verify every labelled object belongs to ``organisation``.

    ``objects`` is an iterable of ``(label, obj)`` pairs for readable errors.
    """

    for label, obj in objects:
        if obj is None:
            continue
        obj_org_id = getattr(obj, "organisation_id", None)
        if obj_org_id is None:
            continue
        if obj_org_id != organisation.id:
            raise TenantIsolationError(
                f"{label} does not belong to organisation {organisation.id}.",
                expected_organisation_id=str(organisation.id),
                actual_organisation_id=str(obj_org_id),
                field=label,
            )
