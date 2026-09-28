from django.db import models
from django.conf import settings
from apps.core.models import TenantModel

class AuditEntry(TenantModel):
    """
    Immutable audit trail record for every privileged or state-changing action.
    Captured in the same database transaction as the primary change.
    """
    actor_id = models.CharField(max_length=128, blank=True, null=True, help_text="User ID or System Worker")
    actor_email = models.EmailField(blank=True, null=True)
    action = models.CharField(max_length=64, help_text="e.g. ALLOCATION_RUN, OVERRIDE, PUBLISH")
    target_entity = models.CharField(max_length=64, help_text="Model/Resource name")
    target_id = models.CharField(max_length=64, help_text="Primary key of target")
    before_state = models.JSONField(blank=True, null=True)
    after_state = models.JSONField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    reason = models.TextField(blank=True, help_text="Mandatory for overrides and manual interventions")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at}] {self.action} on {self.target_entity}:{self.target_id} by {self.actor_email or 'System'}"
