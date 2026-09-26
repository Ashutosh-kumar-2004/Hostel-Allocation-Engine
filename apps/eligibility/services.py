from typing import Tuple, List, Dict, Any
from django.db import transaction
from .models import EligibilityRule, EligibilityResult
from apps.applications.models import Application
from apps.audit.services import AuditService

class EligibilityService:
    @staticmethod
    @transaction.atomic
    def evaluate_application(application: Application) -> Tuple[bool, List[EligibilityResult]]:
        """
        Evaluates a single student application against all configured institutional policy rules for its cycle.
        Deterministic rule checks:
        1. DISTANCE: applicant's distance from campus vs min_distance_km threshold.
        2. ACADEMIC: applicant's CGPA vs min_cgpa threshold.
        3. DISCIPLINARY: proctorial conduct infractions check.
        4. FEE_CLEARED: finance department fee clearance verification.
        """
        rules = list(EligibilityRule.objects.filter(cycle=application.cycle))
        if not rules:
            # Fallback to institutional default rules across cycles if none explicitly attached
            rules = list(EligibilityRule.objects.all())

        overall_eligible = True
        results = []

        for rule in rules:
            passed = True
            reason = "Policy requirement verified."

            # 1. Distance Policy
            if rule.rule_type == "DISTANCE":
                min_distance = float(rule.parameters.get("min_distance_km", 30))
                student_dist = float(application.distance_from_campus_km or 0.0)
                if student_dist >= min_distance:
                    passed = True
                    reason = f"Permanent residence is {student_dist:.1f} km from campus, fulfilling the residency threshold (>= {min_distance:.0f} km)."
                else:
                    passed = False
                    reason = f"Distance from campus ({student_dist:.1f} km) is below the mandatory residency threshold of {min_distance:.0f} km. Classified as local commuter."

            # 2. Academic / CGPA Policy
            elif rule.rule_type == "ACADEMIC":
                min_cgpa = float(rule.parameters.get("min_cgpa", 6.0))
                student_cgpa = float(application.cgpa or 0.0)
                if student_cgpa >= min_cgpa:
                    passed = True
                    reason = f"Academic standing (CGPA {student_cgpa:.2f}) satisfies institutional minimum criteria (>= {min_cgpa:.1f})."
                else:
                    passed = False
                    reason = f"Academic standing (CGPA {student_cgpa:.2f}) is below the required threshold of {min_cgpa:.1f}."

            # 3. Disciplinary Record Policy
            elif rule.rule_type == "DISCIPLINARY":
                if not application.has_disciplinary_record:
                    passed = True
                    reason = "Proctorial clearance confirmed. Zero active disciplinary infractions on record."
                else:
                    passed = False
                    reason = "Active disciplinary conduct violation or proctorial sanction flagged on record."

            # 4. Fee & Financial Clearance Policy
            elif rule.rule_type == "FEE_CLEARED":
                fee_ok = getattr(application, "fee_cleared", True)
                if fee_ok:
                    passed = True
                    reason = "Finance & Accounts office clearance confirmed. All prior semester and mess dues settled."
                else:
                    passed = False
                    reason = "Outstanding university tuition or mess fee arrears detected. Financial hold active."

            # Save atomic evaluation result
            result, _ = EligibilityResult.objects.update_or_create(
                application=application,
                rule=rule,
                defaults={
                    "is_passed": passed,
                    "reason": reason,
                    "institution_id": application.institution_id
                }
            )
            results.append(result)

            # Hard Rule Failure triggers immediate overall ineligibility
            if not passed and rule.is_hard_rule:
                overall_eligible = False

        # Update application status
        new_status = "ELIGIBLE" if overall_eligible else "INELIGIBLE"
        # Only update status if application has not already been permanently published/allocated
        if application.status in ["SUBMITTED", "ELIGIBLE", "INELIGIBLE"]:
            application.status = new_status
            application.save(update_fields=["status", "updated_at"])

        return overall_eligible, results

    @staticmethod
    @transaction.atomic
    def evaluate_all(cycle_id: str = None) -> Dict[str, Any]:
        """
        Executes batch eligibility evaluation across all submitted student applications.
        Returns execution statistics.
        """
        apps_qs = Application.objects.select_related("cycle").all()
        if cycle_id:
            apps_qs = apps_qs.filter(cycle_id=cycle_id)

        total = 0
        eligible_count = 0
        ineligible_count = 0

        for app in apps_qs:
            is_elig, _ = EligibilityService.evaluate_application(app)
            total += 1
            if is_elig:
                eligible_count += 1
            else:
                ineligible_count += 1

        AuditService.record_action(
            action="ELIGIBILITY_BATCH_EVALUATION",
            target_entity="EligibilityRule",
            target_id=str(cycle_id or "ALL"),
            reason=f"Batch evaluation executed for {total} applications. Eligible: {eligible_count}, Ineligible: {ineligible_count}."
        )

        return {
            "total_evaluated": total,
            "eligible_count": eligible_count,
            "ineligible_count": ineligible_count,
        }
