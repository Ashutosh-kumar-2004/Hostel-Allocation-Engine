from django.db import models
from django.utils import timezone
from apps.core.models import TenantModel
from apps.applications.models import AllocationCycle, Application
from apps.inventory.models import Bed

class WaitlistEntry(TenantModel):
    STATUS_CHOICES = [
        ("ACTIVE", "Waiting in Queue"),
        ("OFFERED", "Bed Offered"),
        ("ACCEPTED", "Offer Accepted"),
        ("DECLINED", "Offer Declined"),
        ("EXPIRED", "Offer Expired"),
    ]
    cycle = models.ForeignKey(AllocationCycle, on_delete=models.CASCADE, related_name="waitlist_entries")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="waitlist_entries")
    priority_order = models.PositiveIntegerField(help_text="1 = Next in queue for promotion")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    offered_bed = models.ForeignKey(
        Bed,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="waitlist_offers",
        help_text="Specific bed offered during dynamic vacancy promotion"
    )
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    decision_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, help_text="Reason if student declines offer")

    class Meta:
        ordering = ["priority_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["cycle", "priority_order"],
                condition=models.Q(status__in=["ACTIVE", "OFFERED"]),
                name="unique_active_priority_per_cycle"
            )
        ]

    def __str__(self):
        return f"Waitlist #{self.priority_order}: {self.application.student_name} ({self.get_status_display()})"

    @property
    def is_offer_active(self) -> bool:
        if self.status == "OFFERED" and self.offer_expires_at:
            return timezone.now() <= self.offer_expires_at
        return False

    @property
    def time_remaining_hours(self) -> float:
        if self.status == "OFFERED" and self.offer_expires_at:
            remaining = (self.offer_expires_at - timezone.now()).total_seconds()
            return max(0.0, round(remaining / 3600, 1))
        return 0.0
