from django.db import models
from django.conf import settings
from apps.core.models import TenantModel

class AllocationCycle(TenantModel):
    STATUS_CHOICES = [
        ("DRAFT", "Draft / Configuring"),
        ("OPEN", "Applications Open"),
        ("CLOSED", "Applications Closed"),
        ("PROCESSING", "Allocation In Progress"),
        ("REVIEW", "Warden Review"),
        ("PUBLISHED", "Published"),
        ("ARCHIVED", "Archived"),
    ]
    name = models.CharField(max_length=150, help_text="e.g. AY 2026-27 Autumn Allotment")
    code = models.CharField(max_length=30, unique=True)
    academic_year = models.CharField(max_length=20)
    application_start = models.DateTimeField()
    application_end = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} [{self.get_status_display()}]"


class Application(TenantModel):
    STATUS_CHOICES = [
        ("SUBMITTED", "Submitted"),
        ("ELIGIBLE", "Eligible"),
        ("INELIGIBLE", "Ineligible"),
        ("ALLOCATED", "Allocated in Draft"),
        ("PUBLISHED", "Published Assigned"),
        ("WAITLISTED", "Waitlisted"),
        ("REJECTED", "Rejected"),
    ]
    GENDER_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
        ("O", "Other"),
    ]

    cycle = models.ForeignKey(AllocationCycle, on_delete=models.CASCADE, related_name="applications")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_application"
    )
    # Registration number requirement: 123XXX format
    student_id = models.CharField(max_length=64, db_index=True, help_text="Registration Number (e.g. 123001)")
    student_name = models.CharField(max_length=150)
    student_email = models.EmailField()
    phone_number = models.CharField(max_length=20, blank=True)
    dob = models.DateField(null=True, blank=True, help_text="Date of Birth")
    address = models.TextField(blank=True, help_text="Permanent residential address")
    distance_from_campus_km = models.FloatField(default=50.0, help_text="Distance in KM for eligibility rule")
    cgpa = models.FloatField(default=8.0, help_text="CGPA / Academic score")
    has_disciplinary_record = models.BooleanField(default=False)
    fee_cleared = models.BooleanField(default=True, help_text="Prior Academic & Mess Dues Cleared")
    
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    programme = models.CharField(max_length=100, default="B.Tech Computer Science")
    year_of_study = models.PositiveSmallIntegerField(default=1)
    requires_accessible_room = models.BooleanField(default=False, help_text="Wheelchair / ground floor requirement")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="SUBMITTED")

    class Meta:
        unique_together = ("cycle", "student_id")

    def __str__(self):
        return f"{self.student_name} ({self.student_id}) - {self.cycle.code}"
