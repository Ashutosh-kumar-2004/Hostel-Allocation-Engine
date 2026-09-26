from typing import List, Dict, Any, Tuple
from django.db.models import Count, Q
from .models import Preference
from apps.applications.models import Application
from apps.inventory.models import Hostel

class PreferenceService:
    @staticmethod
    def get_ranked_preferences_for_application(application_id: str) -> List[Preference]:
        """
        Returns all ranked preferences for an application ordered by rank.
        """
        return list(
            Preference.objects.filter(application_id=application_id)
            .select_related("preferred_hostel")
            .order_by("rank")
        )

    @staticmethod
    def check_roommate_mutual_status(app: Application) -> Dict[str, Any]:
        """
        Evaluates mutual roommate request status:
        - MUTUAL_CONFIRMED: Both students requested each other in the same cycle with compatible gender.
        - PENDING_PARTNER: Target student exists & compatible, but has not yet requested this student back.
        - INVALID: Target student does not exist, different gender, or cycle mismatch.
        - NONE: No roommate requested.
        """
        # Find requested roommate ID from any of the student's preferences
        req_roommate_id = (
            Preference.objects.filter(application=app)
            .exclude(preferred_roommate_id__isnull=True)
            .exclude(preferred_roommate_id="")
            .values_list("preferred_roommate_id", flat=True)
            .first()
        )

        if not req_roommate_id:
            return {"status": "NONE", "label": "None specified", "target_id": None, "target_name": None}

        req_roommate_id = req_roommate_id.strip()

        # Reject self-referential roommate request
        if req_roommate_id.lower() == (app.student_id or "").strip().lower():
            return {
                "status": "INVALID",
                "label": "Self-Request Invalid",
                "reason": "You cannot select yourself as a mutual roommate. Roommate co-allocation requires another candidate.",
                "target_id": req_roommate_id,
                "target_name": app.student_name
            }

        # Find target student application in the same cycle
        target_app = Application.objects.filter(cycle=app.cycle, student_id=req_roommate_id).first()
        if not target_app:
            return {
                "status": "INVALID",
                "label": "Candidate Not Found",
                "reason": f"Student ID '{req_roommate_id}' is not registered in this allocation cycle.",
                "target_id": req_roommate_id,
                "target_name": None
            }

        if target_app.id == app.id:
            return {
                "status": "INVALID",
                "label": "Self-Request Invalid",
                "reason": "You cannot select yourself as a mutual roommate. Roommate co-allocation requires another candidate.",
                "target_id": req_roommate_id,
                "target_name": app.student_name
            }

        # Check gender separation compatibility
        if target_app.gender != app.gender:
            return {
                "status": "INVALID",
                "label": "Gender Incompatible",
                "reason": f"Requested candidate {target_app.student_name} ({target_app.get_gender_display()}) does not match your residential gender group ({app.get_gender_display()}).",
                "target_id": req_roommate_id,
                "target_name": target_app.student_name
            }

        # Check if target candidate requested this student back
        target_requests_app = Preference.objects.filter(
            application=target_app,
            preferred_roommate_id=app.student_id
        ).exists()

        if target_requests_app:
            return {
                "status": "MUTUAL_CONFIRMED",
                "label": "Mutual Match Confirmed",
                "reason": f"Both {app.student_name} and {target_app.student_name} requested each other. Co-allocation priority active.",
                "target_id": req_roommate_id,
                "target_name": target_app.student_name,
                "partner_application_id": str(target_app.id)
            }
        else:
            return {
                "status": "PENDING_PARTNER",
                "label": "Pending Partner Confirmation",
                "reason": f"Awaiting {target_app.student_name} ({req_roommate_id}) to select you in their preferences.",
                "target_id": req_roommate_id,
                "target_name": target_app.student_name,
                "partner_application_id": str(target_app.id)
            }

    @staticmethod
    def get_confirmed_mutual_pairs(cycle_id: str = None, hostel_id: str = None) -> List[Dict[str, Any]]:
        """
        Returns a deduplicated list of confirmed mutual roommate pairs for co-allocation,
        optionally scoped to an assigned hostel.
        """
        apps_qs = Application.objects.all()
        if cycle_id:
            apps_qs = apps_qs.filter(cycle_id=cycle_id)

        # Prefetch preferences
        apps = list(apps_qs.prefetch_related("preferences", "preferences__preferred_hostel"))
        app_by_student_id = {a.student_id: a for a in apps}

        pairs = []
        seen = set()

        for a in apps:
            req_id = None
            opted_hostel_ids_a = {str(p.preferred_hostel_id) for p in a.preferences.all()}
            for p in a.preferences.all():
                if p.preferred_roommate_id:
                    req_id = p.preferred_roommate_id.strip()
                    break

            if not req_id or req_id not in app_by_student_id:
                continue

            b = app_by_student_id[req_id]
            if a.id == b.id or a.gender != b.gender:
                continue

            opted_hostel_ids_b = {str(p.preferred_hostel_id) for p in b.preferences.all()}

            # If hostel_id scoping is active (for wardens), at least one student must have opted for this hostel
            if hostel_id and str(hostel_id) not in opted_hostel_ids_a and str(hostel_id) not in opted_hostel_ids_b:
                continue

            # Check if b also requested a
            b_requests_a = any(
                p.preferred_roommate_id and p.preferred_roommate_id.strip() == a.student_id
                for p in b.preferences.all()
            )

            if b_requests_a:
                pair_key = tuple(sorted([a.student_id, b.student_id]))
                if pair_key not in seen:
                    seen.add(pair_key)
                    pairs.append({
                        "student_a": a,
                        "student_b": b,
                        "gender": a.get_gender_display(),
                        "programme_a": a.programme,
                        "programme_b": b.programme,
                    })

        return pairs

    @staticmethod
    def get_demand_analytics(cycle_id: str = None, hostel_id: str = None) -> Dict[str, Any]:
        """
        Calculates aggregate preference demand distribution across hostels and room sharing categories.
        If hostel_id is provided, scopes calculations to that specific hostel (Warden view).
        """
        prefs_qs = Preference.objects.select_related("preferred_hostel", "application")
        if cycle_id:
            prefs_qs = prefs_qs.filter(application__cycle_id=cycle_id)

        if hostel_id:
            prefs_qs = prefs_qs.filter(preferred_hostel_id=hostel_id)
            hostels = Hostel.objects.filter(id=hostel_id)
        else:
            hostels = Hostel.objects.filter(is_active=True)

        total_prefs = prefs_qs.count()
        rank1_prefs = prefs_qs.filter(rank=1)

        # Hostel demand
        hostel_stats = []
        for h in hostels:
            total_for_h = prefs_qs.filter(preferred_hostel=h).count()
            rank1_for_h = rank1_prefs.filter(preferred_hostel=h).count()
            hostel_stats.append({
                "hostel": h,
                "total_demand": total_for_h,
                "rank1_demand": rank1_for_h,
            })

        # Room type demand
        room_types = ["SINGLE", "DOUBLE", "TRIPLE", "DORM"]
        room_stats = {}
        for rt in room_types:
            count = rank1_prefs.filter(preferred_room_type=rt).count()
            room_stats[rt] = count

        mutual_pairs = PreferenceService.get_confirmed_mutual_pairs(cycle_id, hostel_id=hostel_id)

        return {
            "total_preferences": total_prefs,
            "total_first_choices": rank1_prefs.count(),
            "hostel_stats": hostel_stats,
            "room_type_stats": room_stats,
            "confirmed_pairs_count": len(mutual_pairs),
        }

