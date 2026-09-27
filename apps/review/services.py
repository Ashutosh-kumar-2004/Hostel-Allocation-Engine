from typing import Dict, Any, Optional, Tuple, List
from django.db import transaction
from django.db.models import Q
from .models import Override, WardenApproval
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.inventory.models import Bed, Hostel, WardenHostelAssignment
from apps.audit.services import AuditService
from apps.notifications.services import NotificationService

class ReviewService:
    @staticmethod
    @transaction.atomic
    def apply_override(
        assignment_id: str,
        new_bed_id: str,
        warden_id: str,
        warden_email: str,
        reason: str,
        warden_hostel_id: Optional[str] = None
    ) -> Override:
        """
        Manually reassigns a student's bed assignment in an unsealed draft to an unoccupied bed.
        Validates:
        1. Mandatory non-empty justification reason.
        2. Draft status (cannot modify PUBLISHED drafts).
        3. Warden single-hostel ownership scope.
        4. Target bed is unoccupied within the draft.
        5. Hard constraint: Gender policy matching.
        6. Hard constraint: Accessibility priority matching.
        7. Audit logging and in-app notification.
        """
        reason_clean = (reason or "").strip()
        if not reason_clean:
            raise ValueError("Mandatory override reason cannot be empty.")

        assignment = AllocationAssignment.objects.select_for_update().select_related(
            "draft", "application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"
        ).get(id=assignment_id)

        new_bed = Bed.objects.select_for_update().select_related(
            "room", "room__block", "room__block__hostel"
        ).get(id=new_bed_id)
        prev_bed = assignment.bed
        draft = assignment.draft

        if draft.status == "PUBLISHED":
            raise ValueError("Cannot modify assignments on an already sealed and published draft.")

        # 1. Warden Hostel Scope Check
        if warden_hostel_id:
            if str(new_bed.room.block.hostel_id) != str(warden_hostel_id) or str(prev_bed.room.block.hostel_id) != str(warden_hostel_id):
                raise PermissionError("Warden is strictly locked to their assigned hostel and cannot reassign beds to another hostel.")

        # 2. Check that target bed is not already allocated to another applicant in this draft
        if AllocationAssignment.objects.filter(draft=draft, bed=new_bed).exclude(id=assignment.id).exists():
            raise ValueError(f"Target bed {new_bed.bed_identifier} (Room {new_bed.room.room_number}) is already allocated to another applicant in this draft. Use the Resident Swap action instead.")

        # 3. Hard Constraint: Gender Policy Check
        hostel_gender = new_bed.room.block.hostel.gender_type
        student_gender = assignment.application.gender
        is_male = student_gender in ("M", "MALE")
        compat_hostels = ["M", "C"] if is_male else ["W", "F", "C"]
        if hostel_gender not in compat_hostels:
            raise ValueError(f"Gender violation: {assignment.application.student_name} ({assignment.application.get_gender_display()}) cannot be assigned to {new_bed.room.block.hostel.name} ({hostel_gender}).")

        # 4. Hard Constraint: Accessibility Check
        if assignment.application.requires_accessible_room and not new_bed.is_accessible:
            raise ValueError(f"Accessibility violation: {assignment.application.student_name} requires an accessible bed, but Bed {new_bed.bed_identifier} is not ground-floor accessible.")

        override = Override.objects.create(
            assignment=assignment,
            previous_bed=prev_bed,
            new_bed=new_bed,
            warden_id=warden_id,
            warden_email=warden_email,
            mandatory_reason=reason_clean,
            institution_id=assignment.institution_id
        )

        assignment.bed = new_bed
        assignment.explanation = (
            f"Manual warden override applied by {warden_email}. "
            f"Justification: {reason_clean} "
            f"(Previous: {prev_bed.room.block.hostel.name} Room {prev_bed.room.room_number}, Bed {prev_bed.bed_identifier})."
        )
        assignment.save(update_fields=["bed", "explanation", "updated_at"])

        # Cross-cutting audit entry
        AuditService.record_action(
            action="WARDEN_OVERRIDE",
            target_entity="AllocationAssignment",
            target_id=str(assignment.id),
            actor_id=warden_id,
            actor_email=warden_email,
            before_state={
                "bed_id": str(prev_bed.id),
                "room": prev_bed.room.room_number,
                "bed": prev_bed.bed_identifier,
                "hostel": prev_bed.room.block.hostel.name
            },
            after_state={
                "bed_id": str(new_bed.id),
                "room": new_bed.room.room_number,
                "bed": new_bed.bed_identifier,
                "hostel": new_bed.room.block.hostel.name
            },
            reason=reason_clean,
            institution_id=assignment.institution_id
        )

        # In-app notification
        if assignment.application.user:
            NotificationService.send_in_app(
                recipient_user=assignment.application.user,
                subject="Room Reassignment Update (Warden Override)",
                body=f"Your bed has been updated to Bed {new_bed.bed_identifier} in Room {new_bed.room.room_number} ({new_bed.room.block.hostel.name}) following Warden review.",
                notification_type="ALLOCATION_UPDATE",
                action_url="/publication/letter/",
                action_label="View Allotment Status",
                institution_id=draft.institution_id
            )

        return override

    @staticmethod
    @transaction.atomic
    def swap_assignments(
        assignment_a_id: str,
        assignment_b_id: str,
        warden_id: str,
        warden_email: str,
        reason: str,
        warden_hostel_id: Optional[str] = None
    ) -> Tuple[Override, Override]:
        """
        Atomically swaps the bed assignments of two students within the same draft.
        Enforces:
        1. Mandatory non-empty reason.
        2. Both assignments belong to same unsealed draft.
        3. Warden single-hostel ownership.
        4. Cross-gender policy compatibility for both students.
        5. Accessibility compatibility for both students.
        6. Atomic swap respecting UniqueConstraint(draft, bed).
        7. Override records, audit logs, and in-app notifications.
        """
        reason_clean = (reason or "").strip()
        if not reason_clean:
            raise ValueError("Mandatory swap justification reason cannot be empty.")

        if assignment_a_id == assignment_b_id:
            raise ValueError("Cannot swap an assignment with itself.")

        assign_a = AllocationAssignment.objects.select_for_update().select_related(
            "draft", "application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"
        ).get(id=assignment_a_id)

        assign_b = AllocationAssignment.objects.select_for_update().select_related(
            "draft", "application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"
        ).get(id=assignment_b_id)

        if assign_a.draft_id != assign_b.draft_id:
            raise ValueError("Both assignments must belong to the exact same allocation draft.")

        draft = assign_a.draft
        if draft.status == "PUBLISHED":
            raise ValueError("Cannot swap assignments on an already sealed and published draft.")

        bed_a = assign_a.bed
        bed_b = assign_b.bed

        # 1. Warden Hostel Scope Check
        if warden_hostel_id:
            if str(bed_a.room.block.hostel_id) != str(warden_hostel_id) or str(bed_b.room.block.hostel_id) != str(warden_hostel_id):
                raise PermissionError("Warden is strictly locked to their assigned hostel and cannot swap beds across other hostels.")

        # 2. Hard Constraint: Gender Policy Check
        hostel_b_gender = bed_b.room.block.hostel.gender_type
        student_a_male = assign_a.application.gender in ("M", "MALE")
        compat_a = ["M", "C"] if student_a_male else ["W", "F", "C"]
        if hostel_b_gender not in compat_a:
            raise ValueError(f"Gender violation: {assign_a.application.student_name} ({assign_a.application.get_gender_display()}) cannot be moved to {bed_b.room.block.hostel.name} ({hostel_b_gender}).")

        hostel_a_gender = bed_a.room.block.hostel.gender_type
        student_b_male = assign_b.application.gender in ("M", "MALE")
        compat_b = ["M", "C"] if student_b_male else ["W", "F", "C"]
        if hostel_a_gender not in compat_b:
            raise ValueError(f"Gender violation: {assign_b.application.student_name} ({assign_b.application.get_gender_display()}) cannot be moved to {bed_a.room.block.hostel.name} ({hostel_a_gender}).")

        # 3. Hard Constraint: Accessibility Check
        if assign_a.application.requires_accessible_room and not bed_b.is_accessible:
            raise ValueError(f"Accessibility violation: {assign_a.application.student_name} requires an accessible bed, but Bed {bed_b.bed_identifier} (Room {bed_b.room.room_number}) is not accessible.")

        if assign_b.application.requires_accessible_room and not bed_a.is_accessible:
            raise ValueError(f"Accessibility violation: {assign_b.application.student_name} requires an accessible bed, but Bed {bed_a.bed_identifier} (Room {bed_a.room.room_number}) is not accessible.")

        # 4. Atomic Bed Swap satisfying UniqueConstraint(draft, bed)
        temp_bed = Bed.objects.exclude(assignments__draft=draft).first()
        is_temporary_holder = False
        if not temp_bed:
            temp_bed = Bed.objects.create(
                room=bed_a.room,
                bed_identifier="TRANSIT-TEMP",
                status="MAINTENANCE",
                institution_id=draft.institution_id
            )
            is_temporary_holder = True

        # Perform atomic swap through temporary intermediate
        assign_a.bed = temp_bed
        assign_a.save(update_fields=["bed", "updated_at"])

        assign_b.bed = bed_a
        assign_b.explanation = (
            f"Manual resident swap approved by {warden_email}. "
            f"Justification: {reason_clean} (Swapped with {assign_a.application.student_name})."
        )
        assign_b.save(update_fields=["bed", "explanation", "updated_at"])

        assign_a.bed = bed_b
        assign_a.explanation = (
            f"Manual resident swap approved by {warden_email}. "
            f"Justification: {reason_clean} (Swapped with {assign_b.application.student_name})."
        )
        assign_a.save(update_fields=["bed", "explanation", "updated_at"])

        if is_temporary_holder:
            temp_bed.delete()

        # 5. Record Overrides for both residents
        override_a = Override.objects.create(
            assignment=assign_a,
            previous_bed=bed_a,
            new_bed=bed_b,
            warden_id=warden_id,
            warden_email=warden_email,
            mandatory_reason=f"Resident swap with {assign_b.application.student_name} ({assign_b.application.student_id}): {reason_clean}",
            institution_id=draft.institution_id
        )

        override_b = Override.objects.create(
            assignment=assign_b,
            previous_bed=bed_b,
            new_bed=bed_a,
            warden_id=warden_id,
            warden_email=warden_email,
            mandatory_reason=f"Resident swap with {assign_a.application.student_name} ({assign_a.application.student_id}): {reason_clean}",
            institution_id=draft.institution_id
        )

        # 6. Audit Logging
        AuditService.record_action(
            action="WARDEN_RESIDENT_SWAP",
            target_entity="AllocationDraft",
            target_id=str(draft.id),
            actor_id=warden_id,
            actor_email=warden_email,
            before_state={
                "resident_a": {"student_id": assign_a.application.student_id, "bed": bed_a.bed_identifier, "room": bed_a.room.room_number},
                "resident_b": {"student_id": assign_b.application.student_id, "bed": bed_b.bed_identifier, "room": bed_b.room.room_number}
            },
            after_state={
                "resident_a": {"student_id": assign_a.application.student_id, "bed": bed_b.bed_identifier, "room": bed_b.room.room_number},
                "resident_b": {"student_id": assign_b.application.student_id, "bed": bed_a.bed_identifier, "room": bed_a.room.room_number}
            },
            reason=reason_clean,
            institution_id=draft.institution_id
        )

        # 7. In-App Notifications
        if assign_a.application.user:
            NotificationService.send_in_app(
                recipient_user=assign_a.application.user,
                subject="Room Reassignment Update (Warden Resident Swap)",
                body=f"Your bed has been updated to Bed {bed_b.bed_identifier} in Room {bed_b.room.room_number} ({bed_b.room.block.hostel.name}) following Warden review.",
                notification_type="ALLOCATION_UPDATE",
                action_url="/publication/letter/",
                action_label="View Allotment Status",
                institution_id=draft.institution_id
            )

        if assign_b.application.user:
            NotificationService.send_in_app(
                recipient_user=assign_b.application.user,
                subject="Room Reassignment Update (Warden Resident Swap)",
                body=f"Your bed has been updated to Bed {bed_a.bed_identifier} in Room {bed_a.room.room_number} ({bed_a.room.block.hostel.name}) following Warden review.",
                notification_type="ALLOCATION_UPDATE",
                action_url="/publication/letter/",
                action_label="View Allotment Status",
                institution_id=draft.institution_id
            )

        return override_a, override_b

    @staticmethod
    @transaction.atomic
    def approve_draft(
        draft_id: str,
        warden_id: str,
        warden_email: str,
        comments: str = ""
    ) -> WardenApproval:
        """
        Mandatory governance gate: records explicit human approval before any publication can occur.
        Transitions draft status to REVIEWED.
        """
        draft = AllocationDraft.objects.select_for_update().get(id=draft_id)
        if draft.status == "PUBLISHED":
            raise ValueError("Draft is already sealed and published.")

        comments_clean = (comments or "").strip() or "Approved following hostel room audit and review."

        approval, _ = WardenApproval.objects.update_or_create(
            draft=draft,
            defaults={
                "warden_id": warden_id,
                "warden_email": warden_email,
                "comments": comments_clean,
                "is_approved": True,
                "institution_id": draft.institution_id
            }
        )
        draft.status = "REVIEWED"
        draft.save(update_fields=["status", "updated_at"])

        AuditService.record_action(
            action="WARDEN_DRAFT_APPROVAL",
            target_entity="AllocationDraft",
            target_id=str(draft.id),
            actor_id=warden_id,
            actor_email=warden_email,
            reason=f"Warden approved draft for publication readiness: {comments_clean}",
            institution_id=draft.institution_id
        )
        return approval

    @staticmethod
    def get_review_context_for_draft(
        draft: AllocationDraft,
        user,
        query: str = "",
        hostel_filter: Optional[str] = None,
        floor_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Builds complete review context for the warden/admin inspection UI.
        Enforces Warden single-hostel ownership.
        """
        warden_assign = WardenHostelAssignment.objects.filter(user=user).select_related("hostel").first()
        is_scoped_warden = warden_assign is not None and not (user.is_superuser or user.is_staff)
        scoped_hostel = warden_assign.hostel if is_scoped_warden else None

        assignments_qs = AllocationAssignment.objects.filter(draft=draft).select_related(
            "application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel", "bed__room__floor"
        )

        if scoped_hostel:
            assignments_qs = assignments_qs.filter(bed__room__block__hostel=scoped_hostel)
        elif hostel_filter:
            assignments_qs = assignments_qs.filter(bed__room__block__hostel_id=hostel_filter)

        if floor_filter:
            assignments_qs = assignments_qs.filter(bed__room__floor__floor_number=floor_filter)

        if query:
            assignments_qs = assignments_qs.filter(
                Q(application__student_name__icontains=query) |
                Q(application__student_id__icontains=query) |
                Q(bed__room__room_number__icontains=query) |
                Q(bed__bed_identifier__icontains=query)
            )

        assignments = list(assignments_qs.order_by("bed__room__block__hostel__name", "bed__room__room_number", "bed__bed_identifier"))

        # Fetch allocated bed IDs in this draft
        allocated_bed_ids = set(
            AllocationAssignment.objects.filter(draft=draft).values_list("bed_id", flat=True)
        )

        # Vacant beds query within the relevant scope
        vacant_beds_qs = Bed.objects.filter(status="AVAILABLE").exclude(id__in=allocated_bed_ids).select_related(
            "room", "room__block", "room__block__hostel"
        )
        if scoped_hostel:
            vacant_beds_qs = vacant_beds_qs.filter(room__block__hostel=scoped_hostel)
        elif hostel_filter:
            vacant_beds_qs = vacant_beds_qs.filter(room__block__hostel_id=hostel_filter)

        vacant_beds = list(vacant_beds_qs.order_by("room__block__hostel__name", "room__room_number", "bed_identifier"))

        # Overrides performed on this draft
        overrides_qs = Override.objects.filter(assignment__draft=draft).select_related(
            "assignment", "assignment__application", "previous_bed", "previous_bed__room", "previous_bed__room__block__hostel",
            "new_bed", "new_bed__room", "new_bed__room__block__hostel"
        ).order_by("-created_at")

        if scoped_hostel:
            overrides_qs = overrides_qs.filter(
                Q(previous_bed__room__block__hostel=scoped_hostel) |
                Q(new_bed__room__block__hostel=scoped_hostel)
            )

        overrides = list(overrides_qs)

        # Check existing approval
        approval = WardenApproval.objects.filter(draft=draft).first()

        # Hostels for filter dropdown (if admin)
        all_hostels = Hostel.objects.filter(is_active=True).order_by("name")

        return {
            "draft": draft,
            "assignments": assignments,
            "vacant_beds": vacant_beds,
            "overrides": overrides,
            "overrides_count": len(overrides),
            "approval": approval,
            "is_scoped_warden": is_scoped_warden,
            "scoped_hostel": scoped_hostel,
            "all_hostels": all_hostels,
            "query": query,
            "hostel_filter": hostel_filter,
            "floor_filter": floor_filter,
            "total_assigned_scope": len(assignments),
            "total_vacant_scope": len(vacant_beds),
        }
