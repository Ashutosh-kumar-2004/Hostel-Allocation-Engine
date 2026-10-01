import os
import sys
import django

sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from apps.inventory.models import Hostel, Block, Floor, Room, Bed
from apps.applications.models import Application, AllocationCycle
from apps.waitlist.models import WaitlistEntry
from apps.waitlist.services import WaitlistService
from apps.waitlist.views import manual_offer_bed_view
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.review.services import ReviewService
from apps.preferences.views import preferences_list_view

User = get_user_model()
rf = RequestFactory()

def setup_request(req, user):
    req.user = user
    setattr(req, "session", {})
    messages = FallbackStorage(req)
    setattr(req, "_messages", messages)
    return req

def run_tests():
    print("--- STARTING GENDER CONSTRAINT IN DROPDOWNS & ASSIGNMENTS TEST ---")

    admin_user = User.objects.filter(is_superuser=True).first()
    cycle = AllocationCycle.objects.filter(status__in=["ACTIVE", "OPEN"]).first() or AllocationCycle.objects.first()
    assert cycle is not None, "Active allocation cycle not found!"

    # 1. Ensure we have at least one Boys Hostel, one Girls Hostel, and beds in each
    boys_hostel = Hostel.objects.filter(gender_type="M", is_active=True).first()
    girls_hostel = Hostel.objects.filter(gender_type__in=["W", "F"], is_active=True).first()
    assert boys_hostel is not None, "Boys hostel not found!"
    assert girls_hostel is not None, "Girls hostel not found!"

    print(f"Using Boys Hostel: {boys_hostel.name} ({boys_hostel.code}, gender_type={boys_hostel.gender_type})")
    print(f"Using Girls Hostel: {girls_hostel.name} ({girls_hostel.code}, gender_type={girls_hostel.gender_type})")

    # Get a vacant bed in Boys Hostel and Girls Hostel
    boys_bed = Bed.objects.filter(room__block__hostel=boys_hostel, status="AVAILABLE").first()
    girls_bed = Bed.objects.filter(room__block__hostel=girls_hostel, status="AVAILABLE").first()
    assert boys_bed is not None, "Vacant bed in boys hostel not found!"
    assert girls_bed is not None, "Vacant bed in girls hostel not found!"

    # -------------------------------------------------------------
    # TEST 1: Waitlist Manual Offer - Gender Violation Blocked
    # -------------------------------------------------------------
    print("\n[TEST 1] Testing Waitlist Manual Offer gender constraint enforcement...")
    # Find or create a Male student application
    male_app = Application.objects.filter(cycle=cycle, gender="M").first()
    assert male_app is not None, "Male application not found!"
    
    # Create an active waitlist entry for male student if not existing
    waitlist_entry, _ = WaitlistEntry.objects.get_or_create(
        cycle=cycle,
        application=male_app,
        defaults={"priority_order": 999, "status": "ACTIVE"}
    )
    waitlist_entry.status = "ACTIVE"
    waitlist_entry.offered_bed = None
    waitlist_entry.save()

    # Attempt to offer a GIRLS hostel bed to MALE student via WaitlistService
    try:
        WaitlistService.manual_offer_bed(
            entry_id=str(waitlist_entry.id),
            bed_id=str(girls_bed.id),
            warden_user=admin_user,
            reason="Testing gender boundary"
        )
        assert False, "Should have raised ValueError for assigning male student to girls hostel!"
    except ValueError as e:
        print(f"-> SUCCESS: WaitlistService blocked cross-gender offer: {e}")

    # Attempt to offer via view POST request
    req = rf.post(f"/waitlist/offers/{waitlist_entry.id}/manual-offer/", {
        "bed_id": str(girls_bed.id),
        "reason": "Test cross-gender POST"
    })
    setup_request(req, admin_user)
    resp = manual_offer_bed_view(req, entry_id=waitlist_entry.id)
    assert resp.status_code == 302
    waitlist_entry.refresh_from_db()
    assert waitlist_entry.status == "ACTIVE", "Waitlist entry should remain ACTIVE after rejected cross-gender offer!"
    print("-> SUCCESS: View endpoint rejected cross-gender bed offer and kept entry ACTIVE.")

    # Now offer a BOYS bed to MALE student (valid)
    valid_entry = WaitlistService.manual_offer_bed(
        entry_id=str(waitlist_entry.id),
        bed_id=str(boys_bed.id),
        warden_user=admin_user,
        reason="Valid male bed offer"
    )
    assert valid_entry.status == "OFFERED"
    assert valid_entry.offered_bed_id == boys_bed.id
    print(f"-> SUCCESS: Successfully offered matching {boys_hostel.name} bed to {male_app.student_name}.")

    # Reset waitlist entry back
    waitlist_entry.status = "ACTIVE"
    waitlist_entry.offered_bed = None
    waitlist_entry.save()

    # -------------------------------------------------------------
    # TEST 2: Review & Overrides - Reassignment Gender Violation Blocked
    # -------------------------------------------------------------
    print("\n[TEST 2] Testing Draft Review Reassignment gender constraint...")
    draft = AllocationDraft.objects.filter(cycle=cycle).order_by("-created_at").first()
    if draft and draft.status != "PUBLISHED":
        male_assign = AllocationAssignment.objects.filter(draft=draft, application__gender="M").first()
        if male_assign:
            try:
                ReviewService.apply_override(
                    assignment_id=str(male_assign.id),
                    new_bed_id=str(girls_bed.id),
                    warden_id=str(admin_user.id),
                    warden_email="admin@test.edu",
                    reason="Test cross-gender override"
                )
                assert False, "Should have blocked reassigning male student to girls bed!"
            except ValueError as e:
                print(f"-> SUCCESS: ReviewService blocked cross-gender reassignment: {e}")

    # -------------------------------------------------------------
    # TEST 3: Review & Overrides - Cross-Gender Swap Blocked
    # -------------------------------------------------------------
    print("\n[TEST 3] Testing Draft Review Resident Swap cross-gender block...")
    if draft and draft.status != "PUBLISHED":
        male_assign = AllocationAssignment.objects.filter(draft=draft, application__gender="M").first()
        female_assign = AllocationAssignment.objects.filter(draft=draft, application__gender__in=["F", "W"]).first()
        if not female_assign:
            female_app_obj = Application.objects.filter(gender__in=["F", "W"]).first()
            if female_app_obj:
                female_assign = AllocationAssignment.objects.create(
                    draft=draft,
                    application=female_app_obj,
                    bed=girls_bed,
                    score=85.0,
                    rank=1,
                    institution_id="inst_default"
                )
        if male_assign and female_assign:
            try:
                ReviewService.swap_assignments(
                    assignment_a_id=str(male_assign.id),
                    assignment_b_id=str(female_assign.id),
                    warden_id=str(admin_user.id),
                    warden_email="admin@test.edu",
                    reason="Test male-female swap"
                )
                assert False, "Should have blocked resident swap between male and female students!"
            except ValueError as e:
                print(f"-> SUCCESS: ReviewService blocked male-female resident swap: {e}")

    # -------------------------------------------------------------
    # TEST 4: Student Preferences Available Hostels Scope
    # -------------------------------------------------------------
    print("\n[TEST 4] Testing Student Preferences Available Hostels gender filtering...")
    # Verify female user preferences view only includes female & co-ed hostels
    female_user = User.objects.filter(student_application__gender__in=["F", "W"]).first()
    if not female_user:
        # Link Ananya Iyer to a test student user
        female_app_seed = Application.objects.filter(gender__in=["F", "W"]).first()
        if female_app_seed and not female_app_seed.user:
            test_female_user, _ = User.objects.get_or_create(username="test_female_student", email="ananya@university.edu")
            female_app_seed.user = test_female_user
            female_app_seed.save()
            female_user = test_female_user

    if female_user:
        from django.test import Client
        c = Client()
        c.force_login(female_user)
        resp = c.get("/preferences/")
        assert resp.status_code == 200
        html = resp.content.decode()
        for bh in Hostel.objects.filter(gender_type="M"):
            assert f">{bh.name} ({bh.code})<" not in html, f"Boys hostel {bh.name} was rendered in female options!"
        assert girls_hostel.code in html, f"Girls hostel {girls_hostel.code} was not in HTML!"
        print(f"-> SUCCESS: Female student preferences HTML only rendered matching female hostels and excluded all {Hostel.objects.filter(gender_type='M').count()} male hostels.")

    # -------------------------------------------------------------
    # TEST 5: Female Waitlist Manual Offer - Cross Gender Blocked & Matching Allowed
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing Female Student Waitlist Manual Offer...")
    female_app = Application.objects.filter(cycle=cycle, gender__in=["F", "W"]).first()
    if female_app:
        f_waitlist_entry, _ = WaitlistEntry.objects.get_or_create(
            cycle=cycle,
            application=female_app,
            defaults={"priority_order": 998, "status": "ACTIVE"}
        )
        f_waitlist_entry.status = "ACTIVE"
        f_waitlist_entry.offered_bed = None
        f_waitlist_entry.save()

        # Try to offer boys bed to female candidate
        try:
            WaitlistService.manual_offer_bed(
                entry_id=str(f_waitlist_entry.id),
                bed_id=str(boys_bed.id),
                warden_user=admin_user,
                reason="Testing cross-gender offer to female"
            )
            assert False, "Should have blocked boys bed offer to female applicant!"
        except ValueError as e:
            print(f"-> SUCCESS: Blocked boys bed offer to female applicant: {e}")

        # Offer girls bed to female candidate (valid)
        f_valid_entry = WaitlistService.manual_offer_bed(
            entry_id=str(f_waitlist_entry.id),
            bed_id=str(girls_bed.id),
            warden_user=admin_user,
            reason="Valid girls bed offer to female applicant"
        )
        assert f_valid_entry.status == "OFFERED"
        assert f_valid_entry.offered_bed_id == girls_bed.id
        print(f"-> SUCCESS: Valid bed offer in {girls_hostel.name} confirmed for female student {female_app.student_name}.")

        # Reset
        f_waitlist_entry.status = "ACTIVE"
        f_waitlist_entry.offered_bed = None
        f_waitlist_entry.save()

    print("\n=== ALL GENDER CONSTRAINT DROPDOWN & BACKEND TESTS PASSED! ===")

if __name__ == "__main__":
    run_tests()
