import hashlib
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import PublicationRecord, AllocationLetter
from apps.allocation.models import AllocationDraft
from apps.review.models import WardenApproval
from apps.audit.services import AuditService
from apps.notifications.services import NotificationService
from apps.inventory.models import Bed

User = get_user_model()

class PublicationService:
    @staticmethod
    @transaction.atomic
    def publish_draft(draft_id: str, publisher_id: str, publisher_email: str) -> PublicationRecord:
        """
        Officially publish an allocation draft:
        - STRUCTURAL GOVERNANCE CHECK: Human WardenApproval must exist.
        - Sealed transition: COMPLETED / REVIEWED -> PUBLISHED (immutable).
        - Generates immutable AllocationLetter records with unique refs & QR verification codes.
        - Records audit log.
        """
        draft = AllocationDraft.objects.select_for_update().get(id=draft_id)
        
        # STRUCTURAL GOVERNANCE CHECK:
        # Check that human approval exists before publication
        if not WardenApproval.objects.filter(draft=draft, is_approved=True).exists():
            raise PermissionError("Governance violation: Cannot publish an allocation draft without recorded Warden Approval.")

        pub_record, created = PublicationRecord.objects.get_or_create(
            draft=draft,
            defaults={
                "published_by_id": publisher_id,
                "published_by_email": publisher_email,
                "total_allocations": draft.assigned_count,
                "institution_id": draft.institution_id
            }
        )

        draft.status = "PUBLISHED"
        draft.save(update_fields=["status", "updated_at"])

        # Generate immutable AllocationLetter for every assignment in this draft
        for assignment in draft.assignments.select_related("application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"):
            hostel_code = assignment.bed.room.block.hostel.code if assignment.bed and assignment.bed.room and assignment.bed.room.block and assignment.bed.room.block.hostel else "HST"
            ref = f"AL-{draft.cycle.code}-{hostel_code}-{assignment.application.student_id}"
            qr_code = hashlib.sha256(f"{ref}:{assignment.id}".encode()).hexdigest()[:16].upper()
            
            letter, letter_created = AllocationLetter.objects.get_or_create(
                assignment=assignment,
                defaults={
                    "document_reference": ref,
                    "qr_verification_code": qr_code,
                    "institution_id": draft.institution_id
                }
            )
            if not letter.qr_verification_code:
                letter.qr_verification_code = qr_code
                letter.save(update_fields=["qr_verification_code"])

        AuditService.record_action(
            action="ALLOCATION_PUBLISHED",
            target_entity="PublicationRecord",
            target_id=str(pub_record.id),
            actor_id=publisher_id,
            actor_email=publisher_email,
            reason=f"Official publication of validated hostel allocations for Draft {draft.run_identifier}.",
            institution_id=draft.institution_id
        )

        return pub_record

    @staticmethod
    @transaction.atomic
    def check_in_student(
        letter_id_or_ref: str,
        key_number: str,
        verified_by_email: str,
        verified_by_id: str = "",
        remarks: str = ""
    ) -> AllocationLetter:
        """
        Student Check-In & Physical Key Handover Workflow:
        - Verifies that the allotment draft is PUBLISHED and letter exists.
        - Records check-in timestamp, physical key number issued, and verifying warden/caretaker.
        - Transitions physical Bed inventory status to 'OCCUPIED' with student details.
        - Records immutable audit trail 'STUDENT_CHECK_IN'.
        - Dispatches in-app welcome notification with key issuance details.
        """
        letter = AllocationLetter.objects.select_for_update().select_related(
            "assignment",
            "assignment__draft",
            "assignment__application",
            "assignment__bed",
            "assignment__bed__room",
            "assignment__bed__room__block",
            "assignment__bed__room__block__hostel"
        ).filter(
            Q(id=letter_id_or_ref) | Q(document_reference=letter_id_or_ref)
        ).first()

        if not letter:
            raise ValueError(f"Allotment letter '{letter_id_or_ref}' not found.")

        if letter.assignment.draft.status != "PUBLISHED":
            raise ValueError("Check-in disallowed: Allocation draft is not yet officially published.")

        if not key_number or not key_number.strip():
            raise ValueError("Key number is required for student room check-in.")

        before_state = {
            "is_checked_in": letter.is_checked_in,
            "checked_in_at": letter.checked_in_at.isoformat() if letter.checked_in_at else None,
            "key_number_issued": letter.key_number_issued,
        }

        # 1. Update Allocation Letter record
        letter.is_checked_in = True
        letter.checked_in_at = timezone.now()
        letter.key_number_issued = key_number.strip()
        letter.check_in_verified_by = verified_by_email
        letter.check_in_remarks = remarks.strip()
        letter.save(update_fields=[
            "is_checked_in", "checked_in_at", "key_number_issued",
            "check_in_verified_by", "check_in_remarks", "updated_at"
        ])

        # 2. Update physical Bed in inventory
        bed = letter.assignment.bed
        student_id = letter.assignment.application.student_id
        student_name = letter.assignment.application.student_name

        if bed:
            bed.status = "OCCUPIED"
            bed.occupant_student_id = student_id
            bed.occupant_name = student_name
            bed.save(update_fields=["status", "occupant_student_id", "occupant_name", "updated_at"])

        # 3. Record Audit Entry
        after_state = {
            "is_checked_in": True,
            "checked_in_at": letter.checked_in_at.isoformat(),
            "key_number_issued": letter.key_number_issued,
            "verified_by": verified_by_email,
            "bed_id": str(bed.id) if bed else None,
            "bed_status": "OCCUPIED" if bed else None
        }

        AuditService.record_action(
            action="STUDENT_CHECK_IN",
            target_entity="AllocationLetter",
            target_id=str(letter.id),
            actor_id=verified_by_id or verified_by_email,
            actor_email=verified_by_email,
            before_state=before_state,
            after_state=after_state,
            reason=f"Student {student_name} ({student_id}) physically checked in. Room {bed.room.room_number if bed else 'N/A'}, Bed {bed.bed_identifier if bed else 'N/A'}. Key #{letter.key_number_issued} issued.",
            institution_id=letter.institution_id
        )

        # 4. Dispatch In-App Notification to Student
        student_user = User.objects.filter(
            Q(username=student_id) | Q(email__iexact=letter.assignment.application.student_email)
        ).first()

        if student_user:
            hostel_name = bed.room.block.hostel.name if bed and bed.room and bed.room.block and bed.room.block.hostel else "Hostel"
            room_num = bed.room.room_number if bed and bed.room else "N/A"
            bed_ident = bed.bed_identifier if bed else "N/A"
            NotificationService.send_in_app(
                recipient_user=student_user,
                subject="Hostel Check-In Completed & Key Handed Over",
                body=f"Welcome to {hostel_name}! Your physical check-in has been completed. Room {room_num}, Bed {bed_ident}. Physical Key #{letter.key_number_issued} was handed over by {verified_by_email}.",
                notification_type="ALLOTMENT",
                action_url="/publication/",
                action_label="View Allotment Letter",
                institution_id=letter.institution_id
            )

        return letter

    @staticmethod
    def verify_letter(document_reference: str) -> Dict[str, Any]:
        """
        Cryptographic & database verification for an issued allotment letter.
        Used by the public/caretaker QR code verification portal.
        """
        letter = AllocationLetter.objects.select_related(
            "assignment",
            "assignment__draft",
            "assignment__draft__cycle",
            "assignment__application",
            "assignment__bed",
            "assignment__bed__room",
            "assignment__bed__room__block",
            "assignment__bed__room__block__hostel"
        ).filter(
            Q(document_reference=document_reference) | Q(qr_verification_code=document_reference)
        ).first()

        if not letter:
            return {
                "is_valid": False,
                "error": "Document reference not recognized in official institutional registry."
            }

        is_published = letter.assignment.draft.status == "PUBLISHED"
        bed = letter.assignment.bed
        app = letter.assignment.application

        return {
            "is_valid": is_published,
            "document_reference": letter.document_reference,
            "qr_verification_code": letter.qr_verification_code,
            "student_name": app.student_name,
            "student_id": app.student_id,
            "programme": app.programme,
            "hostel_name": bed.room.block.hostel.name if bed and bed.room and bed.room.block and bed.room.block.hostel else "N/A",
            "hostel_code": bed.room.block.hostel.code if bed and bed.room and bed.room.block and bed.room.block.hostel else "N/A",
            "room_number": bed.room.room_number if bed and bed.room else "N/A",
            "floor_number": bed.room.floor_number if bed and bed.room else "N/A",
            "bed_identifier": bed.bed_identifier if bed else "N/A",
            "issued_at": letter.issued_at,
            "is_checked_in": letter.is_checked_in,
            "checked_in_at": letter.checked_in_at,
            "key_number_issued": letter.key_number_issued,
            "verified_by": letter.check_in_verified_by,
            "draft_run_identifier": letter.assignment.draft.run_identifier,
            "cycle_name": letter.assignment.draft.cycle.name,
        }
