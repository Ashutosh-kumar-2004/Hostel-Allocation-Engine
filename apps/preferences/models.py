from django.db import models
from apps.core.models import TenantModel
from apps.applications.models import Application
from apps.inventory.models import Hostel

class Preference(TenantModel):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="preferences")
    rank = models.PositiveSmallIntegerField(help_text="1 = Highest preference")
    preferred_hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    preferred_room_type = models.CharField(
        max_length=20,
        choices=[
            ("SINGLE", "Single Occupancy"),
            ("DOUBLE", "Double Sharing"),
            ("TRIPLE", "Triple Sharing"),
            ("DORM", "Dormitory"),
        ],
        default="DOUBLE"
    )
    preferred_roommate_id = models.CharField(max_length=64, blank=True, null=True, help_text="Mutual roommate request student ID")

    class Meta:
        ordering = ["rank"]
        unique_together = ("application", "rank")

    def __str__(self):
        return f"{self.application.student_name} - Rank #{self.rank}: {self.preferred_hostel.name} ({self.preferred_room_type})"


class RoommateRequest(TenantModel):
    STATUS_CHOICES = [
        ("PENDING", "Pending Confirmation"),
        ("ACCEPTED", "Mutual Confirmed"),
        ("DECLINED", "Declined"),
        ("CANCELLED", "Cancelled"),
    ]
    requester = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="sent_roommate_requests")
    target = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="received_roommate_requests")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    responded_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.requester.student_name} -> {self.target.student_name} ({self.status})"
