"""Abstract model building blocks shared across domains."""

import uuid

from django.db import models


class UUIDModel(models.Model):
    """Gives a model a UUID primary key.

    Externally visible records use UUIDs so sequential internal identifiers
    are never leaked across the API boundary.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    """Adds creation and update timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantScopedModel(models.Model):
    """Abstract base for records owned by exactly one organisation.

    A plain Django foreign key does not guarantee that two related rows share
    an organisation. Code that creates relationships between tenant-scoped
    records must validate the organisation explicitly (see
    ``apps.common.tenancy``) and critical paths should add composite database
    constraints.
    """

    organisation = models.ForeignKey(
        "organisations.Organisation",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
    )

    class Meta:
        abstract = True
