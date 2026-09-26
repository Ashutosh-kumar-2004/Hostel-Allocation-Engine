from django.db import models
from apps.core.models import TenantModel
from apps.applications.models import AllocationCycle, Application

class EligibilityRule(TenantModel):
    RULE_TYPE_CHOICES = [
        ("DISTANCE", "Minimum Distance from University (km)"),
        ("ACADEMIC", "Minimum CGPA / Grade Requirement"),
        ("DISCIPLINARY", "No Pending Disciplinary Record"),
        ("FEE_CLEARED", "Prior Academic Fee Clearance"),
    ]
    cycle = models.ForeignKey(AllocationCycle, on_delete=models.CASCADE, related_name="eligibility_rules")
    name = models.CharField(max_length=120)
    rule_type = models.CharField(max_length=30, choices=RULE_TYPE_CHOICES)
    parameters = models.JSONField(default=dict, help_text="Config parameters (e.g. {'min_distance_km': 30})")
    is_hard_rule = models.BooleanField(default=True, help_text="If true, violation causes automatic ineligibility")

    def __str__(self):
        return f"{self.cycle.code} - {self.name} ({self.rule_type})"


class EligibilityResult(TenantModel):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="eligibility_results")
    rule = models.ForeignKey(EligibilityRule, on_delete=models.CASCADE)
    is_passed = models.BooleanField()
    reason = models.TextField(help_text="Detailed outcome reasoning for transparent audit")

    class Meta:
        unique_together = ("application", "rule")

    def __str__(self):
        status = "PASSED" if self.is_passed else "FAILED"
        return f"{self.application.student_name}: {self.rule.name} -> {status}"
