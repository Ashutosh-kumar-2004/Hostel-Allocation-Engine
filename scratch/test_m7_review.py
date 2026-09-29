import os
import sys
import django

sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.inventory.models import Bed, Hostel, WardenHostelAssignment
from apps.review.models import Override, WardenApproval
from apps.review.services import ReviewService
from apps.publication.services import PublicationService
from apps.audit.models import AuditEntry
from apps.notifications.models import Notification

User = get_user_model()

def run_m7_tests():
    print("=" * 60)
    print("M7 WARDEN DRAFT REVIEW & OVERRIDES VERIFICATION SUITE")
    print("=" * 60)

    # 1. Fetch test draft with assignments
    draft = AllocationDraft.objects.filter(status__in=["COMPLETED", "REVIEWED"], assigned_count__gt=0).first()
    if not draft:
        print("No active draft found. Run M6 first.")
        return

    print(f"Testing on Draft: {draft.run_identifier} (Status: {draft.status})")

    # Fetch admin and warden users
    admin_user = User.objects.filter(username="admin").first()
    warden_user = User.objects.filter(username="rajesh.warden").first() or User.objects.filter(username="warden").first()
    
    # 2. Test Negative Test: Publication Blocked without Approval (P03 Core Rule)
    print("\n--- Testing P03 Governance Gate: Publication without Approval ---")
    WardenApproval.objects.filter(draft=draft).delete()
    draft.status = "COMPLETED"
    draft.save()

    blocked = False
    try:
        PublicationService.publish_draft(
            draft_id=str(draft.id),
            publisher_id=str(admin_user.id),
            publisher_email=admin_user.email
        )
    except PermissionError as e:
        blocked = True
        print(f"[SUCCESS] Publication was blocked as expected! Error: {e}")

    assert blocked, "CRITICAL: Publication succeeded without Warden Approval!"

    # 3. Test Manual Override (Reassign to vacant bed)
    print("\n--- Testing ReviewService.apply_override() ---")
    assignment = draft.assignments.select_related("application", "bed", "bed__room", "bed__room__block__hostel").first()
    prev_bed = assignment.bed
    
    # Find an unoccupied bed matching student gender
    student_gender = assignment.application.gender
    expected_hostel_gender = "M" if student_gender == "M" else "W"
    
    allocated_bed_ids = set(draft.assignments.values_list("bed_id", flat=True))
    vacant_bed = Bed.objects.filter(
        status="AVAILABLE",
        room__block__hostel__gender_type__in=["C", expected_hostel_gender]
    ).exclude(id__in=allocated_bed_ids).first()

    assert vacant_bed is not None, "No vacant bed found for override test"

    override = ReviewService.apply_override(
        assignment_id=str(assignment.id),
        new_bed_id=str(vacant_bed.id),
        warden_id=str(admin_user.id),
        warden_email=admin_user.email,
        reason="Medical ground-floor mobility accommodation authorized by clinic."
    )
    print(f"Override created: {override}")
    assert override.previous_bed_id == prev_bed.id
    assert override.new_bed_id == vacant_bed.id
    
    assignment.refresh_from_db()
    assert assignment.bed_id == vacant_bed.id
    print(f"[SUCCESS] Student {assignment.application.student_name} successfully reassigned to Bed {vacant_bed.bed_identifier}")

    # Verify audit log for override
    audit = AuditEntry.objects.filter(action="WARDEN_OVERRIDE", target_id=str(assignment.id)).first()
    assert audit is not None, "AuditEntry for WARDEN_OVERRIDE missing!"
    print(f"[SUCCESS] Audit entry verified for override: Action={audit.action}")

    # 4. Test Negative Cases on Override
    print("\n--- Testing Negative Cases for Override ---")
    # Empty reason
    empty_reason_blocked = False
    try:
        ReviewService.apply_override(
            assignment_id=str(assignment.id),
            new_bed_id=str(prev_bed.id),
            warden_id=str(admin_user.id),
            warden_email=admin_user.email,
            reason="   "
        )
    except ValueError:
        empty_reason_blocked = True
    assert empty_reason_blocked, "Override with empty reason did not raise ValueError!"
    print("[SUCCESS] Empty justification reason blocked.")

    # Reassigning to already-allocated bed
    other_assignment = draft.assignments.exclude(id=assignment.id).first()
    occupied_bed_blocked = False
    try:
        ReviewService.apply_override(
            assignment_id=str(assignment.id),
            new_bed_id=str(other_assignment.bed_id),
            warden_id=str(admin_user.id),
            warden_email=admin_user.email,
            reason="Attempting to double-allocate"
        )
    except ValueError:
        occupied_bed_blocked = True
    assert occupied_bed_blocked, "Override to already-allocated bed did not raise ValueError!"
    print("[SUCCESS] Reassigning to already-occupied bed blocked (no double allocation).")

    # 5. Test Two-Way Resident Swap
    print("\n--- Testing ReviewService.swap_assignments() ---")
    # Find two male (or two female) assignments in the draft to swap
    cand_a = draft.assignments.filter(application__gender="M").select_related("application", "bed").first()
    cand_b = draft.assignments.filter(application__gender="M").exclude(id=cand_a.id).select_related("application", "bed").first()

    bed_a_orig = cand_a.bed
    bed_b_orig = cand_b.bed

    ov_a, ov_b = ReviewService.swap_assignments(
        assignment_a_id=str(cand_a.id),
        assignment_b_id=str(cand_b.id),
        warden_id=str(admin_user.id),
        warden_email=admin_user.email,
        reason="Mutual room exchange agreed during warden open clinic."
    )
    print(f"Swap executed: {ov_a} and {ov_b}")

    cand_a.refresh_from_db()
    cand_b.refresh_from_db()

    assert cand_a.bed_id == bed_b_orig.id, f"Candidate A should have bed B, got {cand_a.bed_id}"
    assert cand_b.bed_id == bed_a_orig.id, f"Candidate B should have bed A, got {cand_b.bed_id}"
    print(f"[SUCCESS] Two-way resident swap verified: {cand_a.application.student_name} <-> {cand_b.application.student_name}")

    # 6. Test Warden Approval Sign-Off
    print("\n--- Testing ReviewService.approve_draft() ---")
    approval = ReviewService.approve_draft(
        draft_id=str(draft.id),
        warden_id=str(admin_user.id),
        warden_email=admin_user.email,
        comments="Hostel floor inventory audited. Mutual roommate requests preserved. Approved for release."
    )
    assert approval.is_approved == True
    draft.refresh_from_db()
    assert draft.status == "REVIEWED"
    print(f"[SUCCESS] Draft approved! Status: {draft.status} by {approval.warden_email}")

    # Verify audit entry for approval
    audit_appr = AuditEntry.objects.filter(action="WARDEN_DRAFT_APPROVAL", target_id=str(draft.id)).first()
    assert audit_appr is not None
    print(f"[SUCCESS] Audit entry verified for approval: Action={audit_appr.action}")

    # 7. Test Views & HTTP Endpoints
    print("\n--- Testing HTTP Views & Permissions ---")
    client = Client(SERVER_NAME="localhost")
    client.login(username="admin", password="admin123")

    # Review Dashboard
    resp = client.get("/review/")
    assert resp.status_code == 200
    assert "Warden Draft Review" in resp.content.decode("utf-8")
    print("[SUCCESS] GET /review/ -> 200 OK")

    # Draft Review Workspace
    resp_rev = client.get(f"/review/drafts/{draft.id}/")
    assert resp_rev.status_code == 200
    content = resp_rev.content.decode("utf-8")
    assert "Draft Review" in content and "Reallocation Console" in content
    assert "Resident Bed Allocations" in content
    print(f"[SUCCESS] GET /review/drafts/{draft.id}/ -> 200 OK")

    # Overrides Log
    resp_log = client.get(f"/review/drafts/{draft.id}/overrides-log/")
    assert resp_log.status_code == 200
    assert "Recorded Overrides" in resp_log.content.decode("utf-8")
    print(f"[SUCCESS] GET /review/drafts/{draft.id}/overrides-log/ -> 200 OK")

    print("\n" + "=" * 60)
    print("ALL M7 WARDEN REVIEW & OVERRIDES REQUIREMENTS FULLY VERIFIED!")
    print("=" * 60)

if __name__ == "__main__":
    run_m7_tests()
