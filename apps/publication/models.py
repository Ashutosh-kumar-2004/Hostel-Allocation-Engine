from django.db import models
from apps.core.models import TenantModel
from apps.allocation.models import AllocationDraft, AllocationAssignment

class PublicationRecord(TenantModel):
    """
    Enforces governance rule: Drafts cannot be published without recorded human approval.
    """
    draft = models.OneToOneField(AllocationDraft, on_delete=models.CASCADE, related_name="publication_record")
    published_by_id = models.CharField(max_length=64)
    published_by_email = models.EmailField()
    published_at = models.DateTimeField(auto_now_add=True)
    total_allocations = models.PositiveIntegerField()

    def __str__(self):
        return f"Publication for Draft {self.draft.run_identifier} at {self.published_at}"


class AllocationLetter(TenantModel):
    assignment = models.OneToOneField(AllocationAssignment, on_delete=models.CASCADE, related_name="letter")
    document_reference = models.CharField(max_length=100, unique=True)
    pdf_file = models.FileField(upload_to="letters/%Y/%m/", blank=True, null=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    # Student Check-In & Physical Key Handover Workflow (M9)
    is_checked_in = models.BooleanField(default=False, db_index=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    key_number_issued = models.CharField(max_length=50, blank=True, default="")
    check_in_verified_by = models.CharField(max_length=120, blank=True, default="")
    check_in_remarks = models.TextField(blank=True, default="")
    qr_verification_code = models.CharField(max_length=64, blank=True, default="")

    def __str__(self):
        return f"Letter {self.document_reference} ({self.assignment.application.student_name})"

