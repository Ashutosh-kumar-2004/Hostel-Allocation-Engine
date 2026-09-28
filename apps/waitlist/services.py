from datetime import timedelta
from typing import Optional, List, Dict, Any
from django.db import transaction
from django.utils import timezone
from .models import WaitlistEntry
from apps.applications.models import AllocationCycle, Application
from apps.inventory.models import Bed, Hostel
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.audit.services import AuditService
from apps.notifications.services import NotificationService

class WaitlistService:
    @staticmethod
    @transaction.atomic
    def auto_promote_vacancies(
        cycle_id: str,
        hostel_id: Optional[str] = None,
        actor_email: str = "system@university.edu"
    ) -> List[WaitlistEntry]:
        """
        Scans for unoccupied beds and automatically promotes the top eligible candidates
        from the priority queue respecting Hard Constraints (Gender isolation, Accessibility).
        Dispatches a 48-hour bed offer and in-app notification.
        """
        cycle = AllocationCycle.objects.select_for_update().get(id=cycle_id)

        # 1. Identify currently occupied or already-offered beds
        assigned_bed_ids = set(
            AllocationAssignment.objects.filter(
                draft__cycle=cycle,
                draft__status__in=["COMPLETED", "REVIEWED", "PUBLISHED"]
            ).values_list("bed_id", flat=True)
        )

        currently_offered_bed_ids = set(
            WaitlistEntry.objects.filter(
                cycle=cycle,
                status="OFFERED"
            ).exclude(offered_bed__isnull=True).values_list("offered_bed_id", flat=True)
        )

        excluded_bed_ids = assigned_bed_ids.union(currently_offered_bed_ids)

        # 2. Query available vacant beds
        vacant_beds_qs = Bed.objects.filter(status="AVAILABLE").exclude(
            id__in=excluded_bed_ids
        ).select_related("room", "room__block", "room__block__hostel")

        if hostel_id:
            vacant_beds_qs = vacant_beds_qs.filter(room__block__hostel_id=hostel_id)

        vacant_beds = list(vacant_beds_qs.order_by("room__block__hostel__name", "room__room_number", "bed_identifier"))
        if not vacant_beds:
            return []

        # 3. Query active waitlisted candidates in priority order
        active_entries = list(
            WaitlistEntry.objects.select_for_update()
            .filter(cycle=cycle, status="ACTIVE")
            .order_by("priority_order")
            .select_related("application", "application__user", "cycle")
        )
        if not active_entries:
            return []

        promoted_entries = []
        claimed_beds = set()

        for bed in vacant_beds:
            if bed.id in claimed_beds:
                continue

            hostel_gender = bed.room.block.hostel.gender_type

            # Find next eligible candidate in the queue
            candidate_entry = None
            for entry in active_entries:
                if entry.status != "ACTIVE":
                    continue

                app = entry.application

                # Hard Constraint: Gender Isolation
                is_male = app.gender in ("M", "MALE")
                compat_hostels = ["M", "C"] if is_male else ["W", "F", "C"]
                if hostel_gender not in compat_hostels:
                    continue

                # Hard Constraint: Accessibility Priority
                if app.requires_accessible_room and not bed.is_accessible:
                    continue

                candidate_entry = entry
                break

            if candidate_entry:
                # Issue 48-hour bed offer
                candidate_entry.status = "OFFERED"
                candidate_entry.offered_bed = bed
                candidate_entry.offered_at = timezone.now()
                candidate_entry.offer_expires_at = timezone.now() + timedelta(hours=48)
                candidate_entry.save(update_fields=["status", "offered_bed", "offered_at", "offer_expires_at", "updated_at"])

                claimed_beds.add(bed.id)
                promoted_entries.append(candidate_entry)

                # Cross-cutting audit entry
                AuditService.record_action(
                    action="WAITLIST_OFFER_DISPATCHED",
                    target_entity="WaitlistEntry",
                    target_id=str(candidate_entry.id),
                    actor_email=actor_email,
                    before_state={"status": "ACTIVE", "queue_position": candidate_entry.priority_order},
                    after_state={
                        "status": "OFFERED",
                        "offered_bed": bed.bed_identifier,
                        "room": bed.room.room_number,
                        "hostel": bed.room.block.hostel.name,
                        "offer_expires_at": candidate_entry.offer_expires_at.isoformat()
                    },
                    reason=f"Vacancy in {bed.room.block.hostel.name} Room {bed.room.room_number} automatically offered to Queue #{candidate_entry.priority_order}",
                    institution_id=cycle.institution_id
                )

                # Dispatch in-app notification to student
                if candidate_entry.application.user:
                    NotificationService.send_in_app(
                        recipient_user=candidate_entry.application.user,
                        subject="🎉 Hostel Bed Allotment Offered (48h Acceptance Window)",
                        body=f"Great news! A bed vacancy has opened up for you: Bed {bed.bed_identifier} in Room {bed.room.room_number} ({bed.room.block.hostel.name}). Please review and accept your allotment within 48 hours.",
                        notification_type="ALLOCATION_UPDATE",
                        action_url="/waitlist/my-status/",
                        action_label="Review & Accept Bed",
                        institution_id=cycle.institution_id
                    )

        return promoted_entries

    @staticmethod
    @transaction.atomic
    def student_accept_offer(
        entry_id: str,
        user,
        actor_email: Optional[str] = None
    ) -> AllocationAssignment:
        """
        Student accepts their offered bed.
        Atomically:
        1. Confirms the bed assignment in the active draft.
        2. Sets waitlist entry status = 'ACCEPTED'.
        3. Updates application status = 'ALLOCATED'.
        4. Re-indexes remaining active queue entries without gaps.
        5. Logs audit entry and sends congratulatory notification.
        """
        entry = WaitlistEntry.objects.select_for_update().select_related(
            "cycle", "application", "application__user", "offered_bed",
            "offered_bed__room", "offered_bed__room__block", "offered_bed__room__block__hostel"
        ).get(id=entry_id)

        if entry.status != "OFFERED" or not entry.offered_bed:
            raise ValueError("This waitlist entry does not have an active bed offer.")

        if entry.offer_expires_at and timezone.now() > entry.offer_expires_at:
            entry.status = "EXPIRED"
            entry.save(update_fields=["status", "updated_at"])
            raise ValueError("This bed offer has expired. The bed has been released to the next candidate.")

        # Identify draft to attach assignment to
        draft = (
            AllocationDraft.objects.filter(cycle=entry.cycle, status__in=["COMPLETED", "REVIEWED"])
            .order_by("-created_at")
            .first()
            or AllocationDraft.objects.filter(cycle=entry.cycle).order_by("-created_at").first()
        )

        if not draft:
            # Create a dedicated waitlist promotion batch draft if none exists
            draft = AllocationDraft.objects.create(
                cycle=entry.cycle,
                run_identifier=f"WAITLIST-PROMO-{entry.cycle.code}",
                status="COMPLETED",
                institution_id=entry.institution_id
            )

        bed = entry.offered_bed

        # Check if already assigned to someone else
        if AllocationAssignment.objects.filter(draft=draft, bed=bed).exists():
            raise ValueError("Target bed was conflictingly assigned. Please contact the warden.")

        assignment, _ = AllocationAssignment.objects.update_or_create(
            draft=draft,
            application=entry.application,
            defaults={
                "bed": bed,
                "preference_rank_honoured": None,
                "compatibility_score": 0.88,
                "explanation": (
                    f"Allocated via dynamic waitlist vacancy promotion (Queue Position #{entry.priority_order}). "
                    f"Offer accepted by candidate {entry.application.student_name}."
                ),
                "institution_id": entry.institution_id
            }
        )

        # Update application
        entry.application.status = "ALLOCATED"
        entry.application.save(update_fields=["status", "updated_at"])

        # Update waitlist entry
        entry.status = "ACCEPTED"
        entry.decision_at = timezone.now()
        entry.priority_order = 50000 + int(str(entry.id.int)[-4:])
        entry.save(update_fields=["status", "priority_order", "decision_at", "updated_at"])

        # Update draft metrics
        draft.assigned_count += 1
        draft.unassigned_count = max(0, draft.unassigned_count - 1)
        draft.save(update_fields=["assigned_count", "unassigned_count", "updated_at"])

        # Re-index remaining active queue entries
        WaitlistService._reindex_active_queue(entry.cycle)

        # Cross-cutting audit entry
        email = actor_email or (user.email if user else f"{entry.application.student_id}@university.edu")
        AuditService.record_action(
            action="WAITLIST_OFFER_ACCEPTED",
            target_entity="WaitlistEntry",
            target_id=str(entry.id),
            actor_email=email,
            after_state={
                "status": "ACCEPTED",
                "assigned_bed": bed.bed_identifier,
                "room": bed.room.room_number,
                "hostel": bed.room.block.hostel.name
            },
            reason=f"Candidate accepted offered bed {bed.bed_identifier} (Room {bed.room.room_number}). Queue re-indexed.",
            institution_id=entry.institution_id
        )

        # Send in-app notification
        if entry.application.user:
            NotificationService.send_in_app(
                recipient_user=entry.application.user,
                subject="🎉 Hostel Allotment Confirmed!",
                body=f"Your acceptance for Bed {bed.bed_identifier} in Room {bed.room.room_number} ({bed.room.block.hostel.name}) has been confirmed. Your allotment is sealed.",
                notification_type="ALLOCATION_UPDATE",
                action_url="/publication/letter/",
                action_label="View Allotment Letter",
                institution_id=entry.institution_id
            )

        return assignment

    @staticmethod
    @transaction.atomic
    def student_decline_offer(
        entry_id: str,
        user,
        reason: str = "",
        actor_email: Optional[str] = None
    ) -> WaitlistEntry:
        """
        Student declines the offered bed.
        Marks offer as DECLINED, re-indexes queue, and automatically triggers
        auto-promotion to offer the bed to the very next candidate in line.
        """
        entry = WaitlistEntry.objects.select_for_update().select_related(
            "cycle", "application", "offered_bed", "offered_bed__room", "offered_bed__room__block__hostel"
        ).get(id=entry_id)

        if entry.status != "OFFERED":
            raise ValueError("This waitlist entry does not have an active bed offer to decline.")

        declined_bed = entry.offered_bed
        reason_clean = (reason or "").strip() or "Student declined allocation offer."

        entry.status = "DECLINED"
        entry.rejection_reason = reason_clean
        entry.decision_at = timezone.now()
        entry.priority_order = 60000 + int(str(entry.id.int)[-4:])
        entry.save(update_fields=["status", "priority_order", "rejection_reason", "decision_at", "updated_at"])

        # Re-index remaining active queue entries
        WaitlistService._reindex_active_queue(entry.cycle)

        email = actor_email or (user.email if user else f"{entry.application.student_id}@university.edu")
        AuditService.record_action(
            action="WAITLIST_OFFER_DECLINED",
            target_entity="WaitlistEntry",
            target_id=str(entry.id),
            actor_email=email,
            reason=f"Candidate declined offered bed: {reason_clean}",
            institution_id=entry.institution_id
        )

        # Automatically trigger promotion for the newly freed bed to next student!
        WaitlistService.auto_promote_vacancies(
            cycle_id=str(entry.cycle_id),
            hostel_id=str(declined_bed.room.block.hostel_id) if declined_bed else None,
            actor_email="system@university.edu"
        )

        return entry

    @staticmethod
    @transaction.atomic
    def manual_offer_bed(
        entry_id: str,
        bed_id: str,
        warden_user,
        reason: str = ""
    ) -> WaitlistEntry:
        """
        Warden manually offers a specific vacant bed to a waitlisted applicant.
        Validates gender policy and accessibility priority.
        """
        entry = WaitlistEntry.objects.select_for_update().select_related("cycle", "application").get(id=entry_id)
        bed = Bed.objects.select_for_update().select_related("room", "room__block", "room__block__hostel").get(id=bed_id)

        if entry.status != "ACTIVE":
            raise ValueError(f"Cannot offer bed to candidate in status {entry.get_status_display()}. Must be Waiting in Queue.")

        # Check gender policy
        hostel_gender = bed.room.block.hostel.gender_type
        is_male = entry.application.gender in ("M", "MALE")
        compat_hostels = ["M", "C"] if is_male else ["W", "F", "C"]
        if hostel_gender not in compat_hostels:
            raise ValueError(f"Gender violation: {entry.application.student_name} ({entry.application.get_gender_display()}) cannot be assigned to {bed.room.block.hostel.name} ({hostel_gender}).")

        # Check accessibility
        if entry.application.requires_accessible_room and not bed.is_accessible:
            raise ValueError(f"Accessibility violation: Student requires accessible ground floor room, but Bed {bed.bed_identifier} is not accessible.")

        entry.status = "OFFERED"
        entry.offered_bed = bed
        entry.offered_at = timezone.now()
        entry.offer_expires_at = timezone.now() + timedelta(hours=48)
        entry.save(update_fields=["status", "offered_bed", "offered_at", "offer_expires_at", "updated_at"])

        warden_email = warden_user.email or f"{warden_user.username}@university.edu"
        reason_clean = (reason or "").strip() or "Manual bed offer by Warden."

        AuditService.record_action(
            action="WAITLIST_MANUAL_OFFER",
            target_entity="WaitlistEntry",
            target_id=str(entry.id),
            actor_id=str(warden_user.id),
            actor_email=warden_email,
            reason=reason_clean,
            institution_id=entry.institution_id
        )

        if entry.application.user:
            NotificationService.send_in_app(
                recipient_user=entry.application.user,
                subject="Hostel Bed Allotment Offered (Warden Offer)",
                body=f"A bed has been offered to you by Warden: Bed {bed.bed_identifier} in Room {bed.room.room_number} ({bed.room.block.hostel.name}). Please accept within 48 hours.",
                notification_type="ALLOCATION_UPDATE",
                action_url="/waitlist/my-status/",
                action_label="Review Offer",
                institution_id=entry.institution_id
            )

        return entry

    @staticmethod
    def expire_stale_offers(cycle_id: Optional[str] = None) -> int:
        """
        Scans for offered beds where offer_expires_at < now() and expires them.
        Triggers promotion so expired beds immediately flow to the next candidate.
        """
        now = timezone.now()
        stale_qs = WaitlistEntry.objects.filter(status="OFFERED", offer_expires_at__lt=now)
        if cycle_id:
            stale_qs = stale_qs.filter(cycle_id=cycle_id)

        count = 0
        for entry in stale_qs:
            entry.status = "EXPIRED"
            entry.save(update_fields=["status", "updated_at"])
            count += 1
            WaitlistService._reindex_active_queue(entry.cycle)
            WaitlistService.auto_promote_vacancies(str(entry.cycle_id))

        return count

    @staticmethod
    def get_student_waitlist_info(user) -> Optional[Dict[str, Any]]:
        """
        Fetches the waitlist standing and active offer for a student.
        Used on the student portal and navigation bar.
        """
        entry = (
            WaitlistEntry.objects.filter(application__user=user)
            .select_related(
                "cycle", "application", "offered_bed", "offered_bed__room",
                "offered_bed__room__block", "offered_bed__room__block__hostel"
            )
            .order_by("-created_at")
            .first()
        )
        if not entry:
            return None

        # Count active applicants ahead of this student
        ahead_count = 0
        if entry.status == "ACTIVE":
            ahead_count = WaitlistEntry.objects.filter(
                cycle=entry.cycle,
                status="ACTIVE",
                priority_order__lt=entry.priority_order
            ).count()

        return {
            "entry": entry,
            "priority_order": entry.priority_order,
            "status": entry.status,
            "status_display": entry.get_status_display(),
            "ahead_count": ahead_count,
            "is_offered": entry.status == "OFFERED",
            "is_offer_active": entry.is_offer_active,
            "hours_remaining": entry.time_remaining_hours,
            "offered_bed": entry.offered_bed,
        }

    @staticmethod
    def _reindex_active_queue(cycle: AllocationCycle):
        """
        Re-indexes the active queue entries for a cycle to guarantee strictly
        consecutive priority numbers (1, 2, 3...) without gaps or duplicates.
        Uses two-phase update to prevent intermediate unique constraint collisions.
        """
        active_entries = list(
            WaitlistEntry.objects.filter(cycle=cycle, status="ACTIVE")
            .order_by("priority_order", "created_at")
        )
        # Phase 1: Shift to high offset (10000+) to clear 1..1000 namespace
        for idx, e in enumerate(active_entries, start=10000):
            e.priority_order = idx
            e.save(update_fields=["priority_order", "updated_at"])

        # Phase 2: Assign consecutive 1, 2, 3...
        for idx, e in enumerate(active_entries, start=1):
            e.priority_order = idx
            e.save(update_fields=["priority_order", "updated_at"])
