import uuid
from django.db import models
from django.conf import settings

class TimeStampedModel(models.Model):
    """
    Abstract base model providing UUID primary keys and timestamp tracking.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantModel(TimeStampedModel):
    """
    Multi-tenant abstract base model ensuring every domain entity carries an institution_id
    from day one (enabling seamless multi-tenancy without schema changes).
    """
    institution_id = models.CharField(
        max_length=64,
        db_index=True,
        default=getattr(settings, "DEFAULT_INSTITUTION_ID", "inst_default"),
        help_text="Tenant institution identifier"
    )

    class Meta:
        abstract = True
