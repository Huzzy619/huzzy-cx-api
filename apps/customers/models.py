"""Customer and customer identifier models.

A phone number is an identifier, not proof of identity. For fintech customers
transaction data stays in the customer's own payment system; Kora CX stores
only the references and context needed to support the caller.
"""

from __future__ import annotations

from django.db import models

from apps.common.models import TimestampedModel, UUIDModel
from apps.organisations.models import Organisation


class Customer(UUIDModel, TimestampedModel):
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="customers",
    )
    display_name = models.CharField(max_length=200, blank=True)
    external_reference = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["organisation", "external_reference"],
                name="customer_external_ref_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name or str(self.id)


class CustomerIdentifier(UUIDModel, TimestampedModel):
    class Type(models.TextChoices):
        PHONE = "phone", "Phone"
        CRM_ID = "crm_id", "CRM ID"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="customer_identifiers",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="identifiers",
    )
    identifier_type = models.CharField(max_length=20, choices=Type.choices)
    normalized_value = models.CharField(max_length=255)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organisation",
                    "identifier_type",
                    "normalized_value",
                ],
                name="uniq_customer_identifier_per_org",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.identifier_type}:{self.normalized_value}"
