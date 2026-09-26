from django.db import models
from apps.core.models import TenantModel
from apps.applications.models import Application

class CompatibilityResponse(TenantModel):
    """
    Consented lifestyle questionnaire response.
    Values are captured to compute aggregate compatibility scores.
    Raw lifestyle data is protected and never directly exposed to other students.
    """
    SLEEP_HABIT_CHOICES = [
        ("EARLY_BIRD", "Early Bird (sleeps before 11 PM)"),
        ("NIGHT_OWL", "Night Owl (sleeps after 1 AM)"),
        ("FLEXIBLE", "Flexible / Moderate"),
    ]
    STUDY_ENVIRONMENT_CHOICES = [
        ("SILENT", "Absolute Silence"),
        ("LIGHT_MUSIC", "Background Music / Ambient"),
        ("COLLABORATIVE", "Discussion / Group Friendly"),
    ]
    CLEANLINESS_CHOICES = [
        ("VERY_STRICT", "Very Strict / Neat Freak"),
        ("MODERATE", "Moderate Daily Cleaning"),
        ("RELAXED", "Casual / Relaxed"),
    ]
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="compatibility_response")
    sleep_habit = models.CharField(max_length=20, choices=SLEEP_HABIT_CHOICES, default="FLEXIBLE")
    study_environment = models.CharField(max_length=20, choices=STUDY_ENVIRONMENT_CHOICES, default="LIGHT_MUSIC")
    cleanliness_priority = models.CharField(max_length=20, choices=CLEANLINESS_CHOICES, default="MODERATE")
    guest_tolerance_score = models.PositiveSmallIntegerField(default=3, help_text="1 (Low) to 5 (High)")
    consent_recorded = models.BooleanField(default=False, help_text="DPDP Act 2023 Explicit Student Consent")

    def __str__(self):
        return f"Lifestyle Profile: {self.application.student_name}"
