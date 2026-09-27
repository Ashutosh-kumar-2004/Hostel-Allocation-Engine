from django.db import models
from apps.core.models import TenantModel
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.inventory.models import Bed

class Override(TenantModel):
    """
    Every manual warden reallocation requires a documented reason.
    Logs before and after bed assignments.
    """
    assignment = models.ForeignKey(AllocationAssignment, on_delete=models.CASCADE, related_name="overrides")
    previous_bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="overridden_from")
    new_bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="overridden_to")
    warden_id = models.CharField(max_length=64)
    warden_email = models.EmailField()
    mandatory_reason = models.TextField(help_text="Mandatory justification for warden manual reassignment")

    def __str__(self):
        return f"Override on {self.assignment.application.student_name}: {self.previous_bed} -> {self.new_bed}"


class WardenApproval(TenantModel):
    """
    Mandatory governance gate: No allocation draft can be published without an approval record.
    """
    draft = models.OneToOneField(AllocationDraft, on_delete=models.CASCADE, related_name="approval")
    warden_id = models.CharField(max_length=64)
    warden_email = models.EmailField()
    comments = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True)

    def __str__(self):
        return f"Approval for Draft {self.draft.run_identifier} by {self.warden_email}"
