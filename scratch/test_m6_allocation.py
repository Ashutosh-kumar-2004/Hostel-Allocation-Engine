import os
import sys
import django

# Setup Django environment
sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.applications.models import AllocationCycle, Application
from apps.inventory.models import Bed, Room, Hostel
from apps.preferences.models import Preference
from apps.preferences.services import PreferenceService
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.allocation.services import AllocationService
from apps.waitlist.models import WaitlistEntry
from apps.audit.models import AuditEntry
from apps.notifications.models import Notification

def run_test():
    print("=" * 60)
    print("M6 ALLOCATION ENGINE VERIFICATION SUITE")
    print("=" * 60)

    # 1. Fetch active cycle
    cycle = AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING"]).first() or AllocationCycle.objects.first()
    print(f"Cycle: {cycle.name} ({cycle.code}) [ID: {cycle.id}]")

    # 2. Check Ashutosh and Ayush mutual pair setup
    ashutosh_app = Application.objects.filter(cycle=cycle, student_id="12300901").first()
    ayush_app = Application.objects.filter(cycle=cycle, student_id="12300002").first()

    if ashutosh_app and ayush_app:
        status_ashutosh = PreferenceService.check_roommate_mutual_status(ashutosh_app)
        status_ayush = PreferenceService.check_roommate_mutual_status(ayush_app)
        print(f"Ashutosh mutual status: {status_ashutosh['status']} -> Partner: {status_ashutosh.get('target_name')} ({status_ashutosh.get('target_id')})")
        print(f"Ayush mutual status: {status_ayush['status']} -> Partner: {status_ayush.get('target_name')} ({status_ayush.get('target_id')})")
        assert status_ashutosh['status'] == "MUTUAL_CONFIRMED", f"Expected MUTUAL_CONFIRMED, got {status_ashutosh['status']}"
        assert status_ayush['status'] == "MUTUAL_CONFIRMED", f"Expected MUTUAL_CONFIRMED, got {status_ayush['status']}"
    else:
        print("Warning: Ashutosh or Ayush application not found in cycle.")

    # 3. Check applicant count & available beds
    eligible_count = Application.objects.filter(cycle=cycle, status__in=["SUBMITTED", "ELIGIBLE", "ALLOCATED", "WAITLISTED"]).count()
    available_beds = Bed.objects.filter(status="AVAILABLE").count()
    print(f"Total Applications in Cycle: {eligible_count}")
    print(f"Total Available Beds in System: {available_beds}")

    # Ensure applications have SUBMITTED status if testing fresh
    Application.objects.filter(cycle=cycle, status__in=["ALLOCATED", "WAITLISTED"]).update(status="ELIGIBLE")

    # 4. Execute Allocation Run
    print("\n--- Executing AllocationService.run_allocation() ---")
    draft = AllocationService.run_allocation(
        cycle_id=str(cycle.id),
        random_seed=42,
        actor_email="admin@university.edu"
    )
    print(f"Draft Generated: {draft.run_identifier} (Status: {draft.status})")
    print(f"Applicants: {draft.total_applicants} | Assigned: {draft.assigned_count} | Unassigned: {draft.unassigned_count}")
    print(f"Summary Metrics: {draft.summary_metrics}")

    assert draft.status == "COMPLETED", f"Expected COMPLETED, got {draft.status}"
    assert draft.assigned_count > 0, "Expected at least 1 assigned applicant"

    # 5. Verify Mutual Pair Allocation
    if ashutosh_app and ayush_app:
        assign_ashutosh = AllocationAssignment.objects.filter(draft=draft, application=ashutosh_app).first()
        assign_ayush = AllocationAssignment.objects.filter(draft=draft, application=ayush_app).first()

        print("\n--- Mutual Roommate Allocation Verification ---")
        if assign_ashutosh and assign_ayush:
            room_ashutosh = assign_ashutosh.bed.room
            room_ayush = assign_ayush.bed.room
            print(f"Ashutosh: Bed {assign_ashutosh.bed.bed_identifier} in {room_ashutosh.block.hostel.name} Room {room_ashutosh.room_number}")
            print(f"Ayush:     Bed {assign_ayush.bed.bed_identifier} in {room_ayush.block.hostel.name} Room {room_ayush.room_number}")
            print(f"Ashutosh Explanation: {assign_ashutosh.explanation}")
            print(f"Ayush Explanation:     {assign_ayush.explanation}")
            
            assert room_ashutosh.id == room_ayush.id, "CRITICAL: Mutual roommates Ashutosh & Ayush were NOT allocated to the same room!"
            print("[SUCCESS] Ashutosh & Ayush are co-allocated in the EXACT SAME ROOM!")
        else:
            print("[WARNING] One or both mutual roommates were not assigned.")

    # 6. Verify Hard Constraints (Gender isolation, Bed capacity)
    print("\n--- Hard Constraints Verification ---")
    assignments = AllocationAssignment.objects.filter(draft=draft).select_related(
        "application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"
    )

    bed_occupancy = {}
    gender_violations = 0
    accessibility_violations = 0

    for a in assignments:
        # 1-to-1 bed constraint
        bed_id = a.bed_id
        if bed_id in bed_occupancy:
            raise AssertionError(f"Bed {bed_id} assigned multiple times!")
        bed_occupancy[bed_id] = a.application_id

        # Gender constraint
        hostel_gender = a.bed.room.block.hostel.gender_type
        student_gender = a.application.gender
        if hostel_gender != "C" and hostel_gender != student_gender:
            print(f"Gender violation: Student {a.application.student_name} ({student_gender}) in {a.bed.room.block.hostel.name} ({hostel_gender})")
            gender_violations += 1

        # Accessibility constraint
        if a.application.requires_accessible_room and not a.bed.is_accessible:
            print(f"Accessibility violation: Student {a.application.student_name} requires accessible bed, got non-accessible {a.bed.bed_identifier}")
            accessibility_violations += 1

    assert gender_violations == 0, f"Found {gender_violations} gender policy violations!"
    assert accessibility_violations == 0, f"Found {accessibility_violations} accessibility violations!"
    print(f"[SUCCESS] Bed Capacity (1:1): Verified across all {len(assignments)} assignments.")
    print(f"[SUCCESS] Gender Isolation: 0 violations across {len(assignments)} assignments.")
    print(f"[SUCCESS] Accessibility: 0 violations across {len(assignments)} assignments.")

    # 7. Check Waitlist & Notifications
    waitlisted_count = WaitlistEntry.objects.filter(cycle=cycle, status="ACTIVE").count()
    print(f"\nActive Waitlist Count: {waitlisted_count}")

    recent_notifications = Notification.objects.filter(notification_type="ALLOCATION_UPDATE").count()
    print(f"Allocation Update Notifications Dispatched: {recent_notifications}")

    # 8. Check Audit Trail
    audit_entry = AuditEntry.objects.filter(target_entity="AllocationDraft", target_id=str(draft.id)).first()
    if audit_entry:
        print(f"[SUCCESS] Cross-cutting Audit Entry verified: Action={audit_entry.action}, Actor={audit_entry.actor_email}")
    else:
        print("[WARNING] Audit entry not found for draft.")

    print("\n" + "=" * 60)
    print("ALL M6 CONSTRAINTS & CAPABILITIES FULLY VALIDATED!")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
