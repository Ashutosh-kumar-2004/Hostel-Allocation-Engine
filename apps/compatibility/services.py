from typing import Dict, Any, List, Optional
from django.db.models import Count, Avg, Q
from .models import CompatibilityResponse
from apps.applications.models import Application
from apps.preferences.services import PreferenceService

class CompatibilityService:
    @staticmethod
    def calculate_pairwise_score(profile_a: Dict[str, Any], profile_b: Dict[str, Any]) -> float:
        """
        Pure deterministic pairwise compatibility scoring [0.0 - 1.0].
        Weights: Sleep habits (40%), Study habits (30%), Cleanliness (20%), Guest tolerance (10%).
        """
        if not profile_a or not profile_b:
            return 0.50

        score = 0.0
        
        # 1. Sleep habits (40%)
        hab_a = profile_a.get("sleep_habit")
        hab_b = profile_b.get("sleep_habit")
        if hab_a and hab_a == hab_b:
            score += 0.40
        elif "FLEXIBLE" in (hab_a, hab_b):
            score += 0.25
        # Early bird vs Night owl clash scores 0.0

        # 2. Study habits (30%)
        std_a = profile_a.get("study_environment")
        std_b = profile_b.get("study_environment")
        if std_a and std_a == std_b:
            score += 0.30
        elif "LIGHT_MUSIC" in (std_a, std_b):
            score += 0.20
        # Silent vs Collaborative clash scores 0.0

        # 3. Cleanliness (20%)
        cln_a = profile_a.get("cleanliness_priority")
        cln_b = profile_b.get("cleanliness_priority")
        if cln_a and cln_a == cln_b:
            score += 0.20
        elif "MODERATE" in (cln_a, cln_b):
            score += 0.12
        # Very strict vs Relaxed clash scores 0.0

        # 4. Guest tolerance delta (10%)
        gt_a = int(profile_a.get("guest_tolerance_score", 3) or 3)
        gt_b = int(profile_b.get("guest_tolerance_score", 3) or 3)
        diff = abs(gt_a - gt_b)
        score += max(0.0, 0.10 - (diff * 0.025))

        return round(min(1.0, score), 2)

    @staticmethod
    def to_profile_dict(source: Any) -> Dict[str, Any]:
        """
        Converts Application, CompatibilityResponse, or dict into a standard profile dict.
        """
        if not source:
            return {
                "sleep_habit": "FLEXIBLE",
                "study_environment": "LIGHT_MUSIC",
                "cleanliness_priority": "MODERATE",
                "guest_tolerance_score": 3,
                "consent_recorded": False,
            }

        if isinstance(source, dict):
            return {
                "sleep_habit": source.get("sleep_habit", "FLEXIBLE"),
                "study_environment": source.get("study_environment", "LIGHT_MUSIC"),
                "cleanliness_priority": source.get("cleanliness_priority", "MODERATE"),
                "guest_tolerance_score": int(source.get("guest_tolerance_score", 3) or 3),
                "consent_recorded": bool(source.get("consent_recorded", False)),
            }

        # If it's an Application, look up its related response
        if isinstance(source, Application):
            resp = getattr(source, "compatibility_response", None)
            if not resp:
                resp = CompatibilityResponse.objects.filter(application=source).first()
            if resp:
                source = resp
            else:
                return {
                    "sleep_habit": "FLEXIBLE",
                    "study_environment": "LIGHT_MUSIC",
                    "cleanliness_priority": "MODERATE",
                    "guest_tolerance_score": 3,
                    "consent_recorded": False,
                }

        # If it's a CompatibilityResponse
        if isinstance(source, CompatibilityResponse):
            return {
                "sleep_habit": source.sleep_habit,
                "study_environment": source.study_environment,
                "cleanliness_priority": source.cleanliness_priority,
                "guest_tolerance_score": source.guest_tolerance_score,
                "consent_recorded": source.consent_recorded,
            }

        return {
            "sleep_habit": "FLEXIBLE",
            "study_environment": "LIGHT_MUSIC",
            "cleanliness_priority": "MODERATE",
            "guest_tolerance_score": 3,
            "consent_recorded": False,
        }

    @classmethod
    def get_detailed_breakdown(cls, source_a: Any, source_b: Any) -> Dict[str, Any]:
        """
        Calculates a dimension-by-dimension breakdown between two applicants
        strictly preserving DPDP Act 2023 privacy (no raw answer leakage).
        """
        pa = cls.to_profile_dict(source_a)
        pb = cls.to_profile_dict(source_b)

        # 1. Sleep
        if pa["sleep_habit"] == pb["sleep_habit"]:
            sleep_earned = 0.40
            sleep_pct = 100
            sleep_status = "Synchronized"
            sleep_desc = "Optimal schedule alignment with synchronized sleeping and wake-up hours."
        elif "FLEXIBLE" in (pa["sleep_habit"], pb["sleep_habit"]):
            sleep_earned = 0.25
            sleep_pct = 63
            sleep_status = "Complementary"
            sleep_desc = "Flexible lifestyle buffers allow adaptable sleeping arrangements without disruption."
        else:
            sleep_earned = 0.0
            sleep_pct = 0
            sleep_status = "Divergent"
            sleep_desc = "Opposite sleep schedules (Early Bird vs Night Owl) may risk study-time disturbances."

        # 2. Study
        if pa["study_environment"] == pb["study_environment"]:
            study_earned = 0.30
            study_pct = 100
            study_status = "Identical"
            study_desc = "Shared academic ambient expectations in the residence room."
        elif "LIGHT_MUSIC" in (pa["study_environment"], pb["study_environment"]):
            study_earned = 0.20
            study_pct = 67
            study_status = "Compatible"
            study_desc = "Compatible noise tolerances with moderate background study flexibility."
        else:
            study_earned = 0.0
            study_pct = 0
            study_status = "Acoustic Disparity"
            study_desc = "Different study noise preferences (Strict silence vs Collaborative discussion)."

        # 3. Cleanliness
        if pa["cleanliness_priority"] == pb["cleanliness_priority"]:
            clean_earned = 0.20
            clean_pct = 100
            clean_status = "Matching"
            clean_desc = "Identical room upkeep standards and mutual chore division norms."
        elif "MODERATE" in (pa["cleanliness_priority"], pb["cleanliness_priority"]):
            clean_earned = 0.12
            clean_pct = 60
            clean_status = "Acceptable"
            clean_desc = "Balanced hygiene expectations with shared moderate daily cleaning."
        else:
            clean_earned = 0.0
            clean_pct = 0
            clean_status = "Disparity"
            clean_desc = "Noticeable divergence between neat-freak and relaxed tidiness approaches."

        # 4. Guest tolerance
        diff = abs(pa["guest_tolerance_score"] - pb["guest_tolerance_score"])
        guest_earned = max(0.0, 0.10 - (diff * 0.025))
        guest_pct = int((guest_earned / 0.10) * 100)
        if diff == 0:
            guest_status = "Aligned"
            guest_desc = "Identical visitor hosting preferences and personal space boundaries."
        elif diff <= 2:
            guest_status = "Compatible"
            guest_desc = "Minor visitor expectation delta; easily managed through mutual agreement."
        else:
            guest_status = "Disparity"
            guest_desc = "Significant difference in comfort with in-room guest visits."

        total_score = round(min(1.0, sleep_earned + study_earned + clean_earned + guest_earned), 2)
        total_pct = int(round(total_score * 100))

        if total_pct >= 85:
            harmony_level = "EXCEPTIONAL"
            harmony_badge = "bg-emerald-100 text-emerald-800 border-emerald-200"
            harmony_summary = "Outstanding lifestyle synergy. Roommates are ideally matched across sleep, study, and cleanliness norms."
        elif total_pct >= 70:
            harmony_level = "HIGH"
            harmony_badge = "bg-teal-100 text-teal-800 border-teal-200"
            harmony_summary = "Strong lifestyle compatibility. Daily routines are complementary with minimal friction risk."
        elif total_pct >= 55:
            harmony_level = "MODERATE"
            harmony_badge = "bg-amber-100 text-amber-800 border-amber-200"
            harmony_summary = "Balanced compatibility. Manageable minor routine deltas through standard mutual communication."
        else:
            harmony_level = "DIVERGENT"
            harmony_badge = "bg-rose-100 text-rose-800 border-rose-200"
            harmony_summary = "Low lifestyle alignment. High risk of routine disruption; individual room placement or alternative partner recommended."

        return {
            "total_score": total_score,
            "percentage": total_pct,
            "harmony_level": harmony_level,
            "harmony_badge": harmony_badge,
            "harmony_summary": harmony_summary,
            "dimensions": {
                "sleep": {
                    "weight": 40,
                    "earned": round(sleep_earned, 2),
                    "percentage": sleep_pct,
                    "status": sleep_status,
                    "description": sleep_desc,
                },
                "study": {
                    "weight": 30,
                    "earned": round(study_earned, 2),
                    "percentage": study_pct,
                    "status": study_status,
                    "description": study_desc,
                },
                "cleanliness": {
                    "weight": 20,
                    "earned": round(clean_earned, 2),
                    "percentage": clean_pct,
                    "status": clean_status,
                    "description": clean_desc,
                },
                "guest_tolerance": {
                    "weight": 10,
                    "earned": round(guest_earned, 2),
                    "percentage": guest_pct,
                    "status": guest_status,
                    "description": guest_desc,
                },
            },
        }

    @classmethod
    def get_cohort_compatibility_stats(cls, cycle_id: Optional[str] = None, hostel_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates aggregate lifestyle compatibility distributions and DPDP compliance metrics
        scoped by cycle or assigned hostel jurisdiction.
        """
        apps_qs = Application.objects.all()
        if cycle_id:
            apps_qs = apps_qs.filter(cycle_id=cycle_id)

        if hostel_id:
            apps_qs = apps_qs.filter(preferences__preferred_hostel_id=hostel_id).distinct()

        total_apps = apps_qs.count()
        app_ids = list(apps_qs.values_list("id", flat=True))

        responses_qs = CompatibilityResponse.objects.filter(application_id__in=app_ids)
        total_responses = responses_qs.count()
        consented_count = responses_qs.filter(consent_recorded=True).count()
        consent_rate = round((consented_count / max(1, total_apps)) * 100, 1)

        # Sleep distribution
        sleep_counts = {item["sleep_habit"]: item["c"] for item in responses_qs.values("sleep_habit").annotate(c=Count("id"))}
        sleep_dist = [
            {"key": "EARLY_BIRD", "label": "Early Bird", "desc": "Sleeps before 11 PM", "count": sleep_counts.get("EARLY_BIRD", 0), "pct": round(sleep_counts.get("EARLY_BIRD", 0) / max(1, total_responses) * 100, 1)},
            {"key": "NIGHT_OWL", "label": "Night Owl", "desc": "Sleeps after 1 AM", "count": sleep_counts.get("NIGHT_OWL", 0), "pct": round(sleep_counts.get("NIGHT_OWL", 0) / max(1, total_responses) * 100, 1)},
            {"key": "FLEXIBLE", "label": "Flexible", "desc": "Adaptable schedule", "count": sleep_counts.get("FLEXIBLE", 0), "pct": round(sleep_counts.get("FLEXIBLE", 0) / max(1, total_responses) * 100, 1)},
        ]

        # Study distribution
        study_counts = {item["study_environment"]: item["c"] for item in responses_qs.values("study_environment").annotate(c=Count("id"))}
        study_dist = [
            {"key": "SILENT", "label": "Silent Focus", "desc": "Absolute silence required", "count": study_counts.get("SILENT", 0), "pct": round(study_counts.get("SILENT", 0) / max(1, total_responses) * 100, 1)},
            {"key": "LIGHT_MUSIC", "label": "Ambient / Music", "desc": "Low background sound", "count": study_counts.get("LIGHT_MUSIC", 0), "pct": round(study_counts.get("LIGHT_MUSIC", 0) / max(1, total_responses) * 100, 1)},
            {"key": "COLLABORATIVE", "label": "Collaborative", "desc": "Group discussion friendly", "count": study_counts.get("COLLABORATIVE", 0), "pct": round(study_counts.get("COLLABORATIVE", 0) / max(1, total_responses) * 100, 1)},
        ]

        # Cleanliness distribution
        clean_counts = {item["cleanliness_priority"]: item["c"] for item in responses_qs.values("cleanliness_priority").annotate(c=Count("id"))}
        clean_dist = [
            {"key": "VERY_STRICT", "label": "Very Strict", "desc": "Rigorous daily tidiness", "count": clean_counts.get("VERY_STRICT", 0), "pct": round(clean_counts.get("VERY_STRICT", 0) / max(1, total_responses) * 100, 1)},
            {"key": "MODERATE", "label": "Moderate", "desc": "Regular routine cleaning", "count": clean_counts.get("MODERATE", 0), "pct": round(clean_counts.get("MODERATE", 0) / max(1, total_responses) * 100, 1)},
            {"key": "RELAXED", "label": "Casual / Relaxed", "desc": "Low-pressure cleaning", "count": clean_counts.get("RELAXED", 0), "pct": round(clean_counts.get("RELAXED", 0) / max(1, total_responses) * 100, 1)},
        ]

        # Guest tolerance avg
        avg_guest = responses_qs.aggregate(avg=Avg("guest_tolerance_score"))["avg"] or 3.0

        # Cohort Harmony Calculation (sample of peer combinations)
        responses_list = list(responses_qs.values("sleep_habit", "study_environment", "cleanliness_priority", "guest_tolerance_score")[:50])
        pair_scores = []
        for i in range(len(responses_list)):
            for j in range(i + 1, min(i + 6, len(responses_list))):
                pair_scores.append(cls.calculate_pairwise_score(responses_list[i], responses_list[j]))

        avg_harmony = round(sum(pair_scores) / max(1, len(pair_scores)) * 100, 1) if pair_scores else 78.0
        high_affinity_pct = round(len([s for s in pair_scores if s >= 0.75]) / max(1, len(pair_scores)) * 100, 1) if pair_scores else 65.0

        return {
            "total_applicants": total_apps,
            "total_responses": total_responses,
            "consented_count": consented_count,
            "consent_rate": consent_rate,
            "sleep_dist": sleep_dist,
            "study_dist": study_dist,
            "clean_dist": clean_dist,
            "avg_guest_tolerance": round(avg_guest, 1),
            "avg_harmony_pct": avg_harmony,
            "high_affinity_pct": high_affinity_pct,
            "evaluated_pairs_count": len(pair_scores),
        }

    @classmethod
    def get_mutual_pairs_compatibility(cls, cycle_id: Optional[str] = None, hostel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Evaluates real-time pairwise lifestyle compatibility for confirmed mutual roommate pairs.
        """
        pairs = PreferenceService.get_confirmed_mutual_pairs(cycle_id=cycle_id, hostel_id=hostel_id)
        results = []

        for pair in pairs:
            sa = pair["student_a"]
            sb = pair["student_b"]
            breakdown = cls.get_detailed_breakdown(sa, sb)
            results.append({
                "student_a": sa,
                "student_b": sb,
                "score": breakdown["total_score"],
                "percentage": breakdown["percentage"],
                "harmony_level": breakdown["harmony_level"],
                "harmony_badge": breakdown["harmony_badge"],
                "harmony_summary": breakdown["harmony_summary"],
                "dimensions": breakdown["dimensions"],
            })

        # Sort by highest compatibility percentage
        results.sort(key=lambda x: x["percentage"], reverse=True)
        return results
