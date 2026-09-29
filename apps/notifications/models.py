from django.db import models
from django.conf import settings
from apps.core.models import TenantModel

class Notification(TenantModel):
    CHANNEL_CHOICES = [
        ("EMAIL", "Email"),
        ("SMS", "SMS"),
        ("IN_APP", "In-App"),
    ]
    TYPE_CHOICES = [
        ("ROOMMATE_REQUEST", "Roommate Request"),
        ("ROOMMATE_ACCEPTED", "Roommate Accepted"),
        ("ROOMMATE_DECLINED", "Roommate Declined"),
        ("ALLOCATION_UPDATE", "Allocation Update"),
        ("GENERAL", "General Notification"),
    ]
    recipient_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    recipient_email = models.EmailField(blank=True, default="")
    recipient_phone = models.CharField(max_length=20, blank=True, default="")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="IN_APP")
    notification_type = models.CharField(max_length=40, choices=TYPE_CHOICES, default="GENERAL")
    subject = models.CharField(max_length=200)
    body = models.TextField()
    action_url = models.CharField(max_length=255, blank=True, default="")
    action_label = models.CharField(max_length=50, blank=True, default="Review Request & Profile")
    is_read = models.BooleanField(default=False)
    is_sent = models.BooleanField(default=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.channel}] {self.recipient_user or self.recipient_email}: {self.subject}"
