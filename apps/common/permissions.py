"""Permission primitives.

Permissions are defined by action and resource rather than a handful of broad
roles. Roles are templates that grant a set of permission strings; access to a
specific resource is still checked at the resource level.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.common.exceptions import PermissionDeniedError


class Permission:
    """String constants for the actions the platform understands."""

    INTERACTIONS_READ_ASSIGNED = "interactions.read_assigned"
    INTERACTIONS_READ_QUEUE = "interactions.read_queue"
    INTERACTIONS_TRANSFER = "interactions.transfer"
    INTERACTIONS_END = "interactions.end"
    INTERACTIONS_DISPOSITION = "interactions.disposition"

    RECORDINGS_READ = "recordings.read"
    TRANSCRIPTS_READ = "transcripts.read"
    SUMMARIES_REVIEW = "summaries.review"

    QUEUES_CONFIGURE = "queues.configure"
    WORKFLOWS_EDIT = "workflows.edit"
    WORKFLOWS_PUBLISH = "workflows.publish"

    TOOLS_EXECUTE_READ = "tools.execute_read"
    TOOLS_EXECUTE_WRITE = "tools.execute_write"
    TOOLS_APPROVE_SENSITIVE = "tools.approve_sensitive"

    VOICE_AGENTS_READ = "voice_agents.read"
    VOICE_AGENTS_EDIT = "voice_agents.edit"
    VOICE_AGENTS_PUBLISH = "voice_agents.publish"

    AUDIT_READ = "audit.read"
    REPORTS_EXPORT = "reports.export"


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            Permission.INTERACTIONS_READ_QUEUE,
            Permission.QUEUES_CONFIGURE,
            Permission.WORKFLOWS_EDIT,
            Permission.WORKFLOWS_PUBLISH,
            Permission.VOICE_AGENTS_READ,
            Permission.VOICE_AGENTS_EDIT,
            Permission.VOICE_AGENTS_PUBLISH,
            Permission.AUDIT_READ,
            Permission.REPORTS_EXPORT,
        }
    ),
    "admin": frozenset(
        {
            Permission.INTERACTIONS_READ_QUEUE,
            Permission.QUEUES_CONFIGURE,
            Permission.WORKFLOWS_EDIT,
            Permission.WORKFLOWS_PUBLISH,
            Permission.VOICE_AGENTS_READ,
            Permission.VOICE_AGENTS_EDIT,
            Permission.VOICE_AGENTS_PUBLISH,
            Permission.REPORTS_EXPORT,
        }
    ),
    "supervisor": frozenset(
        {
            Permission.INTERACTIONS_READ_QUEUE,
            Permission.INTERACTIONS_TRANSFER,
            Permission.INTERACTIONS_END,
            Permission.RECORDINGS_READ,
            Permission.TRANSCRIPTS_READ,
            Permission.SUMMARIES_REVIEW,
            Permission.VOICE_AGENTS_READ,
            Permission.REPORTS_EXPORT,
        }
    ),
    "agent": frozenset(
        {
            Permission.INTERACTIONS_READ_ASSIGNED,
            Permission.INTERACTIONS_TRANSFER,
            Permission.INTERACTIONS_END,
            Permission.INTERACTIONS_DISPOSITION,
        }
    ),
    "compliance": frozenset(
        {
            Permission.RECORDINGS_READ,
            Permission.TRANSCRIPTS_READ,
            Permission.SUMMARIES_REVIEW,
            Permission.AUDIT_READ,
            Permission.REPORTS_EXPORT,
        }
    ),
}


@dataclass(frozen=True)
class Principal:
    """The authenticated actor for a request.

    ``organisation_id`` is the active tenant resolved from the membership and
    must never be taken from client-supplied input.
    """

    user_id: object
    organisation_id: object
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_role(
        cls, *, user_id, organisation_id, role: str
    ) -> Principal:
        return cls(
            user_id=user_id,
            organisation_id=organisation_id,
            role=role,
            permissions=ROLE_PERMISSIONS.get(role, frozenset()),
        )

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, permission: str) -> None:
        if not self.has_permission(permission):
            raise PermissionDeniedError(
                f"Missing permission: {permission}",
                required_permission=permission,
                role=self.role,
            )
