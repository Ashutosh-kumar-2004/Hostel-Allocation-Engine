import os
import sys
import django

sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from apps.applications.models import AllocationCycle, Application
from apps.inventory.models import Hostel, Block, Room, Bed, WardenHostelAssignment
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.review.models import WardenApproval
from apps.review.services import ReviewService
from apps.publication.models import PublicationRecord, AllocationLetter
from apps.publication.services import PublicationService
from apps.publication.views import (
    publications_view,
    official_allotment_letter_view,
    check_in_student_view,
    verify_document_view
)
from apps.audit.models import AuditEntry
from apps.notifications.models import Notification

User = get_user_model()

def run_m9_tests():
    print("=" * 80)
    print("MODULE 9 TEST SUITE: Publication, Sealed Allotment Orders, and Check-In")
    print("=" * 80)

    # 1. Setup Test Environment
    cycle, _ = AllocationCycle.objects.get_or_create(
        code="AY26-TEST-M9",
        defaults={
            "name": "Test Cycle AY2026-M9",
            "academic_year": "2026-2027",
            "application_start": timezone.now(),
            "application_end": timezone.now() + timezone.timedelta(days=30),
            "status": "PROCESSING",
            "institution_id": "inst_m9"
        }
    )

    hostel_bh4, _ = Hostel.objects.get_or_create(
        code="BH-4-TEST",
        defaults={
            "name": "Boys Hostel 4 Test",
            "gender_type": "M",
            "institution_id": "inst_m9"
        }
    )

    hostel_gh1, _ = Hostel.objects.get_or_create(
        code="GH-1-TEST",
        defaults={
            "name": "Girls Hostel 1 Test",
            "gender_type": "W",
            "institution_id": "inst_m9"
        }
    )

    block_bh4, _ = Block.objects.get_or_create(
        hostel=hostel_bh4,
        code="B-TEST",
        defaults={"name": "Block B Test", "institution_id": "inst_m9"}
    )
    block_gh1, _ = Block.objects.get_or_create(
        hostel=hostel_gh1,
        code="G-TEST",
        defaults={"name": "Block G Test", "institution_id": "inst_m9"}
    )

    room_bh4, _ = Room.objects.get_or_create(
        block=block_bh4,
        room_number="T201",
        defaults={"floor_number": 2, "room_type": "DOUBLE", "cooling_type": "AC", "institution_id": "inst_m9"}
    )
    room_gh1, _ = Room.objects.get_or_create(
        block=block_gh1,
        room_number="G101",
        defaults={"floor_number": 1, "room_type": "SINGLE", "cooling_type": "COOLER", "institution_id": "inst_m9"}
    )

    bed_bh4, _ = Bed.objects.get_or_create(
        room=room_bh4,
        bed_identifier="A",
        defaults={"status": "AVAILABLE", "institution_id": "inst_m9"}
    )
    bed_gh1, _ = Bed.objects.get_or_create(
        room=room_gh1,
        bed_identifier="A",
        defaults={"status": "AVAILABLE", "institution_id": "inst_m9"}
    )

    app_m9_stu1, _ = Application.objects.get_or_create(
        student_id="M9_STU_101",
        cycle=cycle,
        defaults={
            "student_name": "Devrat Test",
            "student_email": "devrat.m9@university.edu",
            "gender": "M",
            "programme": "B.Tech CSE",
            "year_of_study": 3,
            "status": "SUBMITTED",
            "institution_id": "inst_m9"
        }
    )

    app_m9_stu2, _ = Application.objects.get_or_create(
        student_id="M9_STU_102",
        cycle=cycle,
        defaults={
            "student_name": "Pooja Test",
            "student_email": "pooja.m9@university.edu",
            "gender": "F",
            "programme": "M.Tech ECE",
            "year_of_study": 1,
            "status": "SUBMITTED",
            "institution_id": "inst_m9"
        }
    )

    # Users
    u_stu1, _ = User.objects.get_or_create(
        username="M9_STU_101",
        defaults={"email": "devrat.m9@university.edu", "first_name": "Devrat"}
    )
    u_stu1.set_password("Student@123")
    u_stu1.save()

    u_warden_bh4, _ = User.objects.get_or_create(
        username="warden.bh4.test",
        defaults={"email": "warden.bh4.test@university.edu", "first_name": "BH4 Warden"}
    )
    u_warden_bh4.set_password("warden123")
    u_warden_bh4.save()
    WardenHostelAssignment.objects.get_or_create(
        user=u_warden_bh4,
        hostel=hostel_bh4,
        defaults={"warden_email": u_warden_bh4.email, "institution_id": "inst_m9"}
    )

    # Create unapproved draft
    draft_m9, _ = AllocationDraft.objects.get_or_create(
        cycle=cycle,
        run_identifier="RUN-M9-VERIFY-001",
        defaults={
            "status": "COMPLETED",
            "total_applicants": 2,
            "assigned_count": 2,
            "unassigned_count": 0,
            "institution_id": "inst_m9"
        }
    )

    assign_1, _ = AllocationAssignment.objects.get_or_create(
        draft=draft_m9,
        application=app_m9_stu1,
        defaults={"bed": bed_bh4, "compatibility_score": 95.0, "explanation": "M9 Test Allotment", "institution_id": "inst_m9"}
    )
    assign_2, _ = AllocationAssignment.objects.get_or_create(
        draft=draft_m9,
        application=app_m9_stu2,
        defaults={"bed": bed_gh1, "compatibility_score": 90.0, "explanation": "M9 Test Allotment", "institution_id": "inst_m9"}
    )

    # Clean prior approvals/letters for clean test run
    WardenApproval.objects.filter(draft=draft_m9).delete()
    PublicationRecord.objects.filter(draft=draft_m9).delete()
    AllocationLetter.objects.filter(assignment__in=[assign_1, assign_2]).delete()
    draft_m9.status = "COMPLETED"
    draft_m9.save()
    bed_bh4.status = "AVAILABLE"
    bed_bh4.occupant_student_id = ""
    bed_bh4.occupant_name = ""
    bed_bh4.save()
    bed_gh1.status = "AVAILABLE"
    bed_gh1.occupant_student_id = ""
    bed_gh1.occupant_name = ""
    bed_gh1.save()

    # -------------------------------------------------------------
    # TEST 1: P03 Governance Negative Gate (Approval Required)
    # -------------------------------------------------------------
    print("\n[TEST 1] P03 Governance Gate: Publication without approval must fail...")
    try:
        PublicationService.publish_draft(
            draft_id=str(draft_m9.id),
            publisher_id=str(u_warden_bh4.id),
            publisher_email=u_warden_bh4.email
        )
        raise AssertionError("P03 FAIL: publish_draft succeeded without WardenApproval!")
    except PermissionError as pe:
        print(f"  [PASS] Expected PermissionError caught: '{pe}'")

    # -------------------------------------------------------------
    # TEST 2: Warden Approval & Sealing Draft Publication
    # -------------------------------------------------------------
    print("\n[TEST 2] Warden Approval and Official Publication Sealing...")
    approval = ReviewService.approve_draft(
        draft_id=str(draft_m9.id),
        warden_id=str(u_warden_bh4.id),
        warden_email=u_warden_bh4.email,
        comments="Approved following comprehensive room readiness audit."
    )
    assert approval.is_approved is True
    draft_m9.refresh_from_db()
    assert draft_m9.status == "REVIEWED"
    print("  [PASS] Draft successfully transitioned to REVIEWED with human Warden approval.")

    # Now publish
    pub_record = PublicationService.publish_draft(
        draft_id=str(draft_m9.id),
        publisher_id=str(u_warden_bh4.id),
        publisher_email=u_warden_bh4.email
    )
    draft_m9.refresh_from_db()
    assert draft_m9.status == "PUBLISHED", f"Expected PUBLISHED, got {draft_m9.status}"
    assert pub_record.total_allocations == 2
    print(f"  [PASS] Draft sealed as PUBLISHED with PublicationRecord ID: {pub_record.id}")

    # Check Audit log
    audit_pub = AuditEntry.objects.filter(action="ALLOCATION_PUBLISHED", target_id=str(pub_record.id)).first()
    assert audit_pub is not None
    print(f"  [PASS] Immutable Audit entry logged: {audit_pub.action} by {audit_pub.actor_email}")

    # -------------------------------------------------------------
    # TEST 3: Immutable Letter & QR Code Generation
    # -------------------------------------------------------------
    print("\n[TEST 3] Verification of Generated AllocationLetter Records...")
    letters = AllocationLetter.objects.filter(assignment__draft=draft_m9)
    assert letters.count() == 2, f"Expected 2 letters, found {letters.count()}"

    letter_stu1 = letters.filter(assignment=assign_1).first()
    assert letter_stu1 is not None
    assert letter_stu1.document_reference.startswith("AL-AY26-TEST-M9-BH-4-TEST-M9_STU_101")
    assert bool(letter_stu1.qr_verification_code), "QR verification code must not be empty"
    assert letter_stu1.is_checked_in is False
    print(f"  [PASS] Letter 1 created: {letter_stu1.document_reference}")
    print(f"         QR Code Token: {letter_stu1.qr_verification_code}")

    # -------------------------------------------------------------
    # TEST 4: Public / Caretaker QR Verification Service
    # -------------------------------------------------------------
    print("\n[TEST 4] Cryptographic & DB Verification Service...")
    v_result = PublicationService.verify_letter(letter_stu1.document_reference)
    assert v_result["is_valid"] is True
    assert v_result["student_name"] == "Devrat Test"
    assert v_result["student_id"] == "M9_STU_101"
    assert v_result["room_number"] == "T201"
    assert v_result["bed_identifier"] == "A"
    assert v_result["is_checked_in"] is False
    print("  [PASS] Verification query returned valid authentic certificate particulars.")

    # -------------------------------------------------------------
    # TEST 5: Student Check-In & Physical Key Handover Workflow
    # -------------------------------------------------------------
    print("\n[TEST 5] Student Check-In and Key Handover...")
    # Initial bed state
    bed_bh4.refresh_from_db()
    assert bed_bh4.status == "AVAILABLE"

    # Execute check-in
    key_issued = "KEY-T201-A"
    updated_letter = PublicationService.check_in_student(
        letter_id_or_ref=str(letter_stu1.id),
        key_number=key_issued,
        verified_by_email=u_warden_bh4.email,
        verified_by_id=str(u_warden_bh4.id),
        remarks="Student ID verified. Room keys and inventory sheet handed over."
    )

    assert updated_letter.is_checked_in is True
    assert updated_letter.key_number_issued == key_issued
    assert updated_letter.checked_in_at is not None
    assert updated_letter.check_in_verified_by == u_warden_bh4.email
    print(f"  [PASS] AllocationLetter updated: is_checked_in=True, key={updated_letter.key_number_issued}")

    # Verify inventory occupancy update
    bed_bh4.refresh_from_db()
    assert bed_bh4.status == "OCCUPIED", f"Expected OCCUPIED, got {bed_bh4.status}"
    assert bed_bh4.occupant_student_id == "M9_STU_101"
    assert bed_bh4.occupant_name == "Devrat Test"
    print(f"  [PASS] Physical Bed inventory synchronized: status={bed_bh4.status}, occupant={bed_bh4.occupant_name}")

    # Verify audit log
    audit_checkin = AuditEntry.objects.filter(action="STUDENT_CHECK_IN", target_id=str(letter_stu1.id)).first()
    assert audit_checkin is not None
    assert "KEY-T201-A" in audit_checkin.reason
    print(f"  [PASS] Audit entry logged: {audit_checkin.action} - {audit_checkin.reason}")

    # Verify student notification
    notif = Notification.objects.filter(recipient_user=u_stu1, notification_type="ALLOTMENT").order_by("-sent_at").first()
    assert notif is not None
    assert "KEY-T201-A" in notif.body
    print(f"  [PASS] Student in-app notification delivered: '{notif.subject}'")

    # -------------------------------------------------------------
    # TEST 6: Warden Single-Hostel Scope Protection on Check-In
    # -------------------------------------------------------------
    print("\n[TEST 6] Warden Single-Hostel Scope Enforcement...")
    letter_stu2 = letters.filter(assignment=assign_2).first()
    assert letter_stu2 is not None

    factory = RequestFactory()
    req = factory.post(f"/publication/check-in/{letter_stu2.id}/", {"key_number": "KEY-G101-A"})
    req.user = u_warden_bh4
    # Set messages fallback storage
    setattr(req, "session", {})
    messages = FallbackStorage(req)
    setattr(req, "_messages", messages)

    # BH-4 Warden attempting to check in GH-1 student
    resp = check_in_student_view(req, letter_id=letter_stu2.id)
    letter_stu2.refresh_from_db()
    assert letter_stu2.is_checked_in is False, "Cross-hostel check-in must be rejected for scoped warden!"
    print("  [PASS] Cross-hostel check-in attempt by scoped warden correctly blocked.")

    # -------------------------------------------------------------
    # TEST 7: Document View & Public QR Verification HTTP Endpoints
    # -------------------------------------------------------------
    print("\n[TEST 7] HTTP View Endpoints (Document & QR Verification)...")
    req_doc = factory.get(f"/publication/letter/{letter_stu1.document_reference}/")
    req_doc.user = u_stu1
    setattr(req_doc, "session", {})
    setattr(req_doc, "_messages", FallbackStorage(req_doc))
    resp_doc = official_allotment_letter_view(req_doc, document_reference=letter_stu1.document_reference)
    assert resp_doc.status_code == 200
    print("  [PASS] official_allotment_letter_view returned HTTP 200 with printable legal layout.")

    req_verify = factory.get(f"/publication/verify/{letter_stu1.qr_verification_code}/")
    resp_verify = verify_document_view(req_verify, document_reference=letter_stu1.qr_verification_code)
    assert resp_verify.status_code == 200
    print("  [PASS] verify_document_view returned HTTP 200 verification certificate.")

    req_verify_json = factory.get(f"/publication/verify/{letter_stu1.qr_verification_code}/?format=json")
    resp_verify_json = verify_document_view(req_verify_json, document_reference=letter_stu1.qr_verification_code)
    assert resp_verify_json.status_code == 200
    import json
    data = json.loads(resp_verify_json.content)
    assert data["is_valid"] is True
    assert data["is_checked_in"] is True
    assert data["key_number_issued"] == "KEY-T201-A"
    print("  [PASS] JSON API verification returned valid checked-in payload.")

    print("\n" + "=" * 80)
    print("ALL MODULE 9 TESTS PASSED ACCURATELY & COMPLETELY! (EXIT CODE 0)")
    print("=" * 80)

if __name__ == "__main__":
    run_m9_tests()
