import os
import sys
import django

sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test import Client
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.applications.models import AllocationCycle, Application
from apps.inventory.models import Bed, Hostel
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.waitlist.models import WaitlistEntry
from apps.waitlist.services import WaitlistService
from apps.audit.models import AuditEntry
from apps.notifications.models import Notification

User = get_user_model()

def run_m8_tests():
    print("=" * 60)
    print("M8 DYNAMIC VACANCY PROMOTIONS & WAITLIST SUITE")
    print("=" * 60)

    # 1. Fetch active cycle
    cycle = AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING"]).first() or AllocationCycle.objects.first()
    print(f"Cycle: {cycle.name} ({cycle.code})")

    # Fetch admin user
    admin_user = User.objects.filter(username="admin").first()

    # 2. Setup Waitlist Entries for Testing
    # Ensure Candidate 1 and Candidate 2 have standard accessibility to match upper-floor vacancies
    active_entries = list(WaitlistEntry.objects.filter(cycle=cycle, status="ACTIVE").order_by("priority_order"))
    if len(active_entries) < 2:
        # Reset any previous test entries for clean execution
        from django.db import transaction
        with transaction.atomic():
            entries = list(WaitlistEntry.objects.filter(cycle=cycle).order_by("created_at"))
            for idx, e in enumerate(entries, start=1):
                e.status = "ACTIVE"
                e.offered_bed = None
                e.rejection_reason = ""
                e.priority_order = idx + 1000 # avoid temporary conflict
                e.save()
            for idx, e in enumerate(entries, start=1):
                e.priority_order = idx
                e.save()
        active_entries = list(WaitlistEntry.objects.filter(cycle=cycle, status="ACTIVE").order_by("priority_order"))

    assert len(active_entries) >= 2, "Need at least 2 waitlist entries for full testing"
    
    # Candidate 1: standard (requires_accessible_room = False)
    cand1 = active_entries[0]
    cand1.application.requires_accessible_room = False
    cand1.application.save()

    # Candidate 2: requires_accessible_room = False
    cand2 = active_entries[1]
    cand2.application.requires_accessible_room = False
    cand2.application.save()

    # Candidate 3 (if exists): requires_accessible_room = True (to test accessibility protection)
    if len(active_entries) >= 3:
        cand3 = active_entries[2]
        cand3.application.requires_accessible_room = True
        cand3.application.save()

    print(f"Active Waitlist Entries in Cycle: {len(active_entries)}")
    print(f"Priority #1: {cand1.application.student_name} (Accessible: {cand1.application.requires_accessible_room})")
    print(f"Priority #2: {cand2.application.student_name} (Accessible: {cand2.application.requires_accessible_room})")

    # 3. Test Auto-Promotion of Vacancies
    print("\n--- Testing WaitlistService.auto_promote_vacancies() ---")
    promoted = WaitlistService.auto_promote_vacancies(
        cycle_id=str(cycle.id),
        actor_email="admin@university.edu"
    )
    print(f"Promoted count: {len(promoted)}")
    assert len(promoted) > 0, "Expected at least 1 promotion offer"

    first_offer = promoted[0]
    print(f"Candidate #{first_offer.priority_order}: {first_offer.application.student_name}")
    print(f"Offered Bed: Bed {first_offer.offered_bed.bed_identifier} (Room {first_offer.offered_bed.room.room_number}, {first_offer.offered_bed.room.block.hostel.name})")
    print(f"Offer Status: {first_offer.status} | Expires At: {first_offer.offer_expires_at}")
    print(f"Hours Remaining: {first_offer.time_remaining_hours}h")

    assert first_offer.status == "OFFERED"
    assert first_offer.offered_bed is not None
    assert first_offer.is_offer_active == True

    # Verify Hard Constraints on offered bed
    hostel_gender = first_offer.offered_bed.room.block.hostel.gender_type
    assert hostel_gender in ["C", first_offer.application.gender], "Gender violation on offered bed!"
    if first_offer.application.requires_accessible_room:
        assert first_offer.offered_bed.is_accessible, "Accessibility violation on offered bed!"

    print("[SUCCESS] Hard constraints verified on auto-promoted bed offer.")

    # Verify audit entry & notifications
    audit_offer = AuditEntry.objects.filter(action="WAITLIST_OFFER_DISPATCHED", target_id=str(first_offer.id)).first()
    assert audit_offer is not None, "AuditEntry for WAITLIST_OFFER_DISPATCHED missing!"
    print(f"[SUCCESS] Audit entry verified: Action={audit_offer.action}")

    # 4. Test Student Accepting the Offer
    print("\n--- Testing WaitlistService.student_accept_offer() ---")
    student_user = first_offer.application.user
    assignment = WaitlistService.student_accept_offer(
        entry_id=str(first_offer.id),
        user=student_user,
        actor_email=admin_user.email
    )
    first_offer.refresh_from_db()

    print(f"Offer Status: {first_offer.status} (Decision at: {first_offer.decision_at})")
    print(f"Created Assignment: {assignment}")
    assert first_offer.status == "ACCEPTED"
    assert assignment.bed_id == first_offer.offered_bed_id
    assert first_offer.application.status == "ALLOCATED"
    print(f"[SUCCESS] Candidate {first_offer.application.student_name} accepted offer and received confirmed assignment!")

    # Verify audit entry for acceptance
    audit_accept = AuditEntry.objects.filter(action="WAITLIST_OFFER_ACCEPTED", target_id=str(first_offer.id)).first()
    assert audit_accept is not None, "AuditEntry for WAITLIST_OFFER_ACCEPTED missing!"
    print(f"[SUCCESS] Audit entry verified: Action={audit_accept.action}")

    # Verify queue re-indexing (consecutive 1, 2, 3...)
    remaining_active = list(WaitlistEntry.objects.filter(cycle=cycle, status="ACTIVE").order_by("priority_order"))
    for idx, e in enumerate(remaining_active, start=1):
        assert e.priority_order == idx, f"Queue priority gap found! Expected {idx}, got {e.priority_order}"
    print(f"[SUCCESS] Remaining {len(remaining_active)} active queue entries strictly re-indexed without gaps.")

    # 5. Test Student Declining an Offer & Auto-Promoting next candidate
    print("\n--- Testing WaitlistService.student_decline_offer() ---")
    # If there is another active candidate, promote and test decline
    if remaining_active:
        promoted_next = WaitlistService.auto_promote_vacancies(cycle_id=str(cycle.id), actor_email="admin@university.edu")
        if promoted_next:
            decline_target = promoted_next[0]
            declined_bed = decline_target.offered_bed
            declined_entry = WaitlistService.student_decline_offer(
                entry_id=str(decline_target.id),
                user=decline_target.application.user,
                reason="Opted for off-campus housing."
            )
            assert declined_entry.status == "DECLINED"
            print(f"[SUCCESS] Candidate declined offer: Status={declined_entry.status}, Reason='{declined_entry.rejection_reason}'")

            # Verify audit entry for decline
            audit_dec = AuditEntry.objects.filter(action="WAITLIST_OFFER_DECLINED", target_id=str(declined_entry.id)).first()
            assert audit_dec is not None, "AuditEntry for WAITLIST_OFFER_DECLINED missing!"
            print(f"[SUCCESS] Audit entry verified for decline: Action={audit_dec.action}")

    # 6. Test HTTP Views & Permissions
    print("\n--- Testing HTTP Views & Endpoints ---")
    client = Client(SERVER_NAME="localhost")

    # A. Warden / Admin Waitlist Hub
    client.login(username="admin", password="admin123")
    resp_hub = client.get("/waitlist/")
    assert resp_hub.status_code == 200
    content_hub = resp_hub.content.decode("utf-8")
    assert "Waiting List" in content_hub
    assert "Auto-Promote Next Vacancies" in content_hub
    print("[SUCCESS] GET /waitlist/ -> 200 OK (Warden Hub)")

    # B. Auto-promote POST endpoint
    resp_promote = client.post("/waitlist/auto-promote/", {"cycle_id": str(cycle.id)}, follow=True)
    assert resp_promote.status_code == 200
    print("[SUCCESS] POST /waitlist/auto-promote/ -> 200 OK")

    # C. Student Waitlist Tracking Portal
    client.logout()
    student_with_entry = WaitlistEntry.objects.filter(application__user__isnull=False).first()
    if student_with_entry and student_with_entry.application.user:
        u = student_with_entry.application.user
        client.force_login(u)
        resp_portal = client.get("/waitlist/my-status/")
        assert resp_portal.status_code == 200
        content_portal = resp_portal.content.decode("utf-8")
        assert "Waiting List" in content_portal
        print(f"[SUCCESS] GET /waitlist/my-status/ -> 200 OK (Student: {u.username})")

    # D. Test Context Processor Badges
    from apps.core.context_processors import user_roles
    class FakeReq:
        user = admin_user
    ctx = user_roles(FakeReq())
    assert "active_waitlist_count" in ctx
    print(f"[SUCCESS] Global Context Processor verified: active_waitlist_count={ctx['active_waitlist_count']}")

    print("\n" + "=" * 60)
    print("ALL M8 DYNAMIC VACANCY PROMOTIONS & WAITLIST TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    run_m8_tests()
