from django.db import models
from django.conf import settings
from apps.core.models import TenantModel
from apps.applications.models import AllocationCycle, Application
from apps.inventory.models import Bed

class AllocationDraft(TenantModel):
    """
    Every allocation run produces a draft first.
    The Draft -> Published state transition requires explicit human approval.
    """
    STATUS_CHOICES = [
        ("IN_PROGRESS", "Solving / Computing"),
        ("COMPLETED", "Draft Generated"),
        ("REVIEWED", "Warden Reviewed"),
        ("PUBLISHED", "Published Final"),
        ("FAILED", "Run Failed"),
    ]
    cycle = models.ForeignKey(AllocationCycle, on_delete=models.CASCADE, related_name="drafts")
    run_identifier = models.CharField(max_length=64, unique=True)
    random_seed = models.PositiveIntegerField(default=42, help_text="Stored seed ensures 100% reproducible tiebreaks")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="IN_PROGRESS")
    total_applicants = models.PositiveIntegerField(default=0)
    assigned_count = models.PositiveIntegerField(default=0)
    unassigned_count = models.PositiveIntegerField(default=0)
    summary_metrics = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Draft {self.run_identifier} ({self.cycle.code}) [{self.get_status_display()}]"


class AllocationAssignment(TenantModel):
    """
    A specific bed assignment inside a draft.
    Guaranteed unique bed per draft at database level via UniqueConstraint.
    """
    draft = models.ForeignKey(AllocationDraft, on_delete=models.CASCADE, related_name="assignments")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="assignments")
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="assignments")
    preference_rank_honoured = models.PositiveSmallIntegerField(null=True, blank=True)
    compatibility_score = models.FloatField(null=True, blank=True)
    explanation = models.TextField(help_text="Detailed explanation of why this bed was allocated")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["draft", "bed"], name="unique_bed_per_draft"),
            models.UniqueConstraint(fields=["draft", "application"], name="unique_application_per_draft")
        ]

    def __str__(self):
        return f"{self.application.student_name} -> {self.bed} (Draft: {self.draft.run_identifier})"


class SavedSimulationScenario(TenantModel):
    """
    Stores What-If Simulation outcome snapshots in strict isolation.
    Does NOT update or touch real inventory beds, real applications, or published allocations.
    """
    hostel = models.ForeignKey("inventory.Hostel", on_delete=models.CASCADE, related_name="saved_simulations")
    cycle = models.ForeignKey(AllocationCycle, on_delete=models.SET_NULL, null=True, blank=True, related_name="saved_simulations")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saved_simulations"
    )
    name = models.CharField(max_length=150, default="Scenario Snapshot")
    seed = models.PositiveIntegerField(default=88213)
    pref_weight = models.PositiveSmallIntegerField(default=65)
    comp_weight = models.PositiveSmallIntegerField(default=35)
    reserved_quota = models.PositiveSmallIntegerField(default=15)
    hypo_block = models.CharField(max_length=64, blank=True)
    hypo_cooling = models.CharField(max_length=64, blank=True)
    excluded_blocks = models.JSONField(default=list, blank=True)
    
    # Stored result metrics & bed allocation map
    result_metrics = models.JSONField(default=dict, blank=True)
    simulated_allocations = models.JSONField(default=dict, blank=True)  # bed_id -> {status, occupant, student_id}

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Simulation {self.name} ({self.hostel.code}) - Seed {self.seed}"

