import uuid
from typing import Dict, Any, Optional
from django.db import transaction
from .models import AllocationDraft, AllocationAssignment
from .engine import AllocationEngine, ApplicantData, BedData
from apps.applications.models import Application, AllocationCycle
from apps.inventory.models import Bed
from apps.preferences.models import Preference
from apps.preferences.services import PreferenceService
from apps.notifications.services import NotificationService
from apps.waitlist.models import WaitlistEntry
from apps.audit.services import AuditService

class AllocationService:
    @staticmethod
    @transaction.atomic
    def run_allocation(
        cycle_id: str,
        random_seed: int = 42,
        actor_email: str = "system@university.edu",
        hostel_id: Optional[str] = None
    ) -> AllocationDraft:
        """
        Executes the M6 Allocation Engine run:
        - Atomic mutual roommate pairing
        - Accessibility hard constraints
        - Ranked preference matching with M5 lifestyle synergy optimization
        - Atomically persists assignments, updates applications, populates waitlist, and dispatches notifications
        """
        cycle = AllocationCycle.objects.select_for_update().get(id=cycle_id)
        
        run_id = f"RUN-{cycle.code}-{uuid.uuid4().hex[:6].upper()}"
        draft = AllocationDraft.objects.create(
            cycle=cycle,
            run_identifier=run_id,
            random_seed=random_seed,
            status="IN_PROGRESS",
            institution_id=cycle.institution_id
        )

        # 1. Fetch eligible applications
        apps_qs = Application.objects.filter(
            cycle=cycle,
            status__in=["SUBMITTED", "ELIGIBLE"]
        ).select_related("compatibility_response", "user")

        if hostel_id:
            apps_qs = apps_qs.filter(preferences__preferred_hostel_id=hostel_id).distinct()

        applications = list(apps_qs)
        applicant_data_list = []

        for app in applications:
            prefs = list(Preference.objects.filter(application=app).select_related("preferred_hostel").order_by("rank"))
            pref_tuples = [(str(p.preferred_hostel_id), p.preferred_room_type) for p in prefs]
            compat = getattr(app, "compatibility_response", None)
            lifestyle_dict = {
                "sleep_habit": compat.sleep_habit,
                "study_environment": compat.study_environment,
                "cleanliness_priority": compat.cleanliness_priority,
                "guest_tolerance_score": compat.guest_tolerance_score,
            } if compat else {}

            # Check confirmed mutual roommate from M4/M5
            mutual_status = PreferenceService.check_roommate_mutual_status(app)
            mutual_id = (
                mutual_status.get("target_id")
                if mutual_status.get("status") == "MUTUAL_CONFIRMED"
                else None
            )

            applicant_data_list.append(
                ApplicantData(
                    application_id=str(app.id),
                    student_id=app.student_id,
                    student_name=app.student_name,
                    gender=app.gender,
                    requires_accessible=app.requires_accessible_room,
                    preferences=pref_tuples,
                    lifestyle=lifestyle_dict,
                    mutual_roommate_id=mutual_id
                )
            )

        # 2. Fetch available beds
        beds_qs = Bed.objects.filter(status="AVAILABLE").select_related(
            "room", "room__block", "room__block__hostel"
        )
        if hostel_id:
            beds_qs = beds_qs.filter(room__block__hostel_id=hostel_id)

        available_beds = list(beds_qs)
        bed_data_list = [
            BedData(
                bed_id=str(b.id),
                bed_identifier=b.bed_identifier,
                hostel_id=str(b.room.block.hostel_id),
                hostel_name=b.room.block.hostel.name,
                hostel_gender=b.room.block.hostel.gender_type,
                room_id=str(b.room_id),
                room_number=b.room.room_number,
                room_type=b.room.room_type,
                cooling_type=b.room.cooling_type,
                is_accessible=b.is_accessible,
                room_capacity=b.room.capacity
            )
            for b in available_beds
        ]

        # 3. Solve using pure-python engine with mutual roommate & lifestyle synergy
        engine = AllocationEngine(random_seed=random_seed)
        result = engine.solve(applicants=applicant_data_list, beds=bed_data_list)

        # 4. Atomically persist assignments
        app_map = {str(app.id): app for app in applications}
        bed_map = {str(b.id): b for b in available_beds}

        assignment_objs = []
        for assignment in result.assignments:
            app_obj = app_map[assignment.application_id]
            bed_obj = bed_map[assignment.bed_id]
            assign_record = AllocationAssignment(
                draft=draft,
                application=app_obj,
                bed=bed_obj,
                preference_rank_honoured=assignment.preference_rank,
                compatibility_score=assignment.compatibility_score,
                explanation=assignment.explanation,
                institution_id=cycle.institution_id
            )
            assignment_objs.append(assign_record)

            app_obj.status = "ALLOCATED"
            app_obj.save(update_fields=["status", "updated_at"])

            # Send in-app notification to student
            if app_obj.user:
                NotificationService.send_in_app(
                    recipient_user=app_obj.user,
                    subject=f"Hostel Allocation Draft Ready ({draft.run_identifier})",
                    body=f"You have been allocated Bed {bed_obj.bed_identifier} in Room {bed_obj.room.room_number} ({bed_obj.room.block.hostel.name}). Your allocation is in Draft awaiting Warden Review.",
                    notification_type="ALLOCATION_UPDATE",
                    action_url=f"/publication/letter/",
                    action_label="View Allotment Status",
                    institution_id=cycle.institution_id
                )

        AllocationAssignment.objects.bulk_create(assignment_objs)

        # 5. Populate Waitlist for unassigned applications (M8 Integration)
        for priority_idx, unassigned_app_id in enumerate(result.unassigned_applications, start=1):
            u_app = app_map[unassigned_app_id]
            u_app.status = "WAITLISTED"
            u_app.save(update_fields=["status", "updated_at"])

            WaitlistEntry.objects.update_or_create(
                cycle=cycle,
                application=u_app,
                defaults={
                    "priority_order": priority_idx,
                    "status": "ACTIVE",
                    "institution_id": cycle.institution_id
                }
            )

            if u_app.user:
                NotificationService.send_in_app(
                    recipient_user=u_app.user,
                    subject=f"Allocation Waitlist Update: Queue #{priority_idx}",
                    body=f"Preferences exhausted for current cycle. You have been placed at position #{priority_idx} on the active waitlist. Automatic promotion will trigger if vacancies arise.",
                    notification_type="ALLOCATION_UPDATE",
                    action_url="/waitlist/",
                    action_label="View Waitlist",
                    institution_id=cycle.institution_id
                )

        # 6. Save draft status & summary metrics
        draft.total_applicants = len(applicant_data_list)
        draft.assigned_count = len(result.assignments)
        draft.unassigned_count = len(result.unassigned_applications)
        draft.summary_metrics = {
            "mutual_pairs_honoured": result.mutual_pairs_honoured,
            "rank1_honoured_count": result.rank1_honoured_count,
            "average_compatibility": result.average_compatibility_score,
            "capacity_utilization_pct": round(len(result.assignments) / max(1, len(available_beds)) * 100, 1),
            "satisfaction_rate_pct": round(len(result.assignments) / max(1, len(applicant_data_list)) * 100, 1),
        }
        draft.status = "COMPLETED"
        draft.save()

        # 7. Cross-cutting audit log entry
        AuditService.record_action(
            action="ALLOCATION_RUN",
            target_entity="AllocationDraft",
            target_id=str(draft.id),
            actor_email=actor_email,
            after_state={
                "run_identifier": draft.run_identifier,
                "assigned": draft.assigned_count,
                "unassigned": draft.unassigned_count,
                "mutual_pairs_honoured": result.mutual_pairs_honoured,
                "average_compatibility": result.average_compatibility_score,
            },
            reason=f"Automated allocation run completed for cycle {cycle.code} (Seed: {random_seed})",
            institution_id=cycle.institution_id
        )

        return draft


class SimulationExecutionService:
    """
    Business Logic Service for What-If Allocation Simulations.
    Extracts queries, aggregations, input validations, and real applicant
    transformations out of the view to keep the view layer thin and maintainable.
    """
    @staticmethod
    def get_hostel_context(current_hostel):
        from apps.inventory.models import Block, Floor, Room, Bed
        from apps.applications.models import AllocationCycle
        from django.db.models import Prefetch

        active_cycle = AllocationCycle.objects.filter(status="OPEN").first() or AllocationCycle.objects.first()

        blocks = Block.objects.filter(hostel=current_hostel).prefetch_related(
            Prefetch("floors", queryset=Floor.objects.order_by("floor_number")),
            Prefetch(
                "rooms",
                queryset=Room.objects.filter(is_active=True).select_related("floor").prefetch_related("beds").order_by("room_number")
            )
        ).order_by("name")

        hostel_beds_qs = Bed.objects.filter(
            room__block__hostel=current_hostel,
            room__is_active=True
        ).select_related("room", "room__block", "room__block__hostel")

        baseline_total = hostel_beds_qs.count()
        baseline_occupied = hostel_beds_qs.filter(status="OCCUPIED").count()
        baseline_available = hostel_beds_qs.filter(status="AVAILABLE").count()
        baseline_reserved = hostel_beds_qs.filter(status="RESERVED").count()
        baseline_maintenance = hostel_beds_qs.filter(status="MAINTENANCE").count()

        baseline_stats = {
            "total_beds": baseline_total,
            "occupied": baseline_occupied,
            "available": baseline_available,
            "reserved": baseline_reserved,
            "maintenance": baseline_maintenance,
        }

        baseline_block_occupancies = []
        for blk in blocks:
            b_beds = hostel_beds_qs.filter(room__block=blk)
            t_cnt = b_beds.count()
            o_cnt = b_beds.filter(status="OCCUPIED").count()
            p_val = round((o_cnt / t_cnt * 100), 1) if t_cnt else 0.0
            baseline_block_occupancies.append({
                "block": blk,
                "total": t_cnt,
                "occupied": o_cnt,
                "pct": p_val
            })

        from .simulation import SimulationBed
        sim_beds = [
            SimulationBed(
                bed_id=str(b.id),
                bed_identifier=b.bed_identifier,
                room_number=b.room.room_number,
                floor_number=b.room.floor_number or (b.room.floor.floor_number if b.room.floor else 0),
                block_code=b.room.block.code,
                block_name=b.room.block.name,
                hostel_code=b.room.block.hostel.code,
                hostel_gender=b.room.block.hostel.gender_type,
                cooling_type=b.room.cooling_type,
                room_type=b.room.room_type,
                is_accessible=b.is_accessible,
                baseline_status=b.status,
                baseline_occupant=b.occupant_name or "",
                baseline_student_id=b.occupant_student_id or ""
            )
            for b in hostel_beds_qs
        ]

        return {
            "active_cycle": active_cycle,
            "blocks": blocks,
            "baseline_stats": baseline_stats,
            "baseline_block_occupancies": baseline_block_occupancies,
            "sim_beds": sim_beds
        }

    @staticmethod
    def load_real_applicants(current_hostel, active_cycle, max_limit: int = 150):
        """
        Loads real students from the database:
        Queries Application, Preference, and CompatibilityResponse tables.
        Falls back to gender-matching cycle applicants if specific hostel preference isn't ranked #1.
        """
        from apps.applications.models import Application
        from apps.preferences.models import Preference
        from .simulation import SimulationApplicant

        # 1. Fetch applications for current cycle matching hostel gender
        target_gender = current_hostel.gender_type
        apps_qs = Application.objects.select_related(
            "cycle", "user"
        ).prefetch_related(
            "preferences__preferred_hostel",
            "compatibility_response"
        )

        if active_cycle:
            apps_qs = apps_qs.filter(cycle=active_cycle)

        if target_gender in ["M", "W", "F"]:
            g = "M" if target_gender == "M" else ("W" if target_gender in ["W", "F"] else target_gender)
            apps_qs = apps_qs.filter(gender__in=[g, target_gender])

        real_applications = list(apps_qs[:max_limit])
        sim_applicants = []

        for app in real_applications:
            # First preference
            first_pref = app.preferences.filter(rank=1).first()
            if not first_pref:
                first_pref = app.preferences.first()

            pref_hostel_code = first_pref.preferred_hostel.code if first_pref and first_pref.preferred_hostel else current_hostel.code
            pref_room_type = first_pref.preferred_room_type if first_pref else "DOUBLE"
            pref_cooling = "AC" if (getattr(first_pref, "preferred_room_type", "") == "SINGLE" or app.requires_accessible_room) else "COOLER"

            # Compute lifestyle compatibility base score from real questionnaire
            compat_score = 0.75
            compat_resp = getattr(app, "compatibility_response", None)
            if compat_resp:
                # Calculate real base score from sleep and cleanliness traits
                score_mod = 0.0
                if compat_resp.sleep_habit == "EARLY_BIRD":
                    score_mod += 0.05
                if compat_resp.cleanliness_priority == "VERY_STRICT":
                    score_mod += 0.05
                if compat_resp.guest_tolerance_score >= 3:
                    score_mod += 0.04
                compat_score = min(0.95, 0.70 + score_mod)

            sim_applicants.append(
                SimulationApplicant(
                    student_id=app.student_id,
                    student_name=app.student_name,
                    gender=app.gender,
                    requires_accessible=app.requires_accessible_room,
                    preferred_hostel_code=pref_hostel_code,
                    preferred_cooling=pref_cooling,
                    preferred_room_type=pref_room_type,
                    is_reserved_category=(app.cgpa < 8.0 or app.distance_from_campus_km > 250),
                    compatibility_score=compat_score
                )
            )

        return sim_applicants

    @staticmethod
    def validate_and_execute_simulation(post_data, sim_beds, sim_applicants):
        """
        Validates POST parameters:
        - Safe integer conversion with fallbacks
        - Bounds checking (pref_weight 0-100, quota 0-40, seed 1-999999)
        - Server-side reconciliation ensuring pref_weight + comp_weight == 100
        - Bounds on sample size
        """
        from .simulation import WhatIfSimulationService

        try:
            pref_weight = int(post_data.get("pref_weight", 65))
        except (ValueError, TypeError):
            pref_weight = 65
        pref_weight = max(0, min(100, pref_weight))

        # Reconcile server-side: comp_weight strictly equals 100 - pref_weight
        comp_weight = 100 - pref_weight

        try:
            reserved_quota = int(post_data.get("reserved_quota", 15))
        except (ValueError, TypeError):
            reserved_quota = 15
        reserved_quota = max(0, min(40, reserved_quota))

        try:
            seed_val = int(post_data.get("seed", 88213))
        except (ValueError, TypeError):
            seed_val = 88213
        seed_val = max(1, min(9999999, seed_val))

        hypothetical_block = post_data.get("hypo_block", "")
        hypothetical_cooling = post_data.get("hypo_cooling", "No change")
        if hasattr(post_data, "getlist"):
            excluded_blocks = post_data.getlist("excluded_blocks")
        else:
            raw_ex = post_data.get("excluded_blocks", [])
            excluded_blocks = raw_ex if isinstance(raw_ex, list) else [raw_ex] if raw_ex else []

        # Slice sample size to available real applicants with safe ceiling
        try:
            req_sample = int(post_data.get("sample_size", len(sim_applicants)))
            req_sample = max(1, min(len(sim_applicants), min(500, req_sample)))
        except (ValueError, TypeError):
            req_sample = len(sim_applicants)

        active_applicants = sim_applicants[:req_sample] if sim_applicants else []

        result = WhatIfSimulationService.run_simulation(
            applicants=active_applicants,
            beds=sim_beds,
            pref_weight=pref_weight,
            comp_weight=comp_weight,
            reserved_quota_pct=reserved_quota,
            excluded_block_codes=excluded_blocks,
            hypothetical_block=hypothetical_block,
            hypothetical_cooling=hypothetical_cooling,
            random_seed=seed_val
        )

        return {
            "result": result,
            "pref_weight": pref_weight,
            "comp_weight": comp_weight,
            "reserved_quota": reserved_quota,
            "hypo_block": hypothetical_block,
            "hypo_cooling": hypothetical_cooling,
            "excluded_blocks": excluded_blocks,
            "seed_val": seed_val,
            "applicant_count": len(active_applicants)
        }

