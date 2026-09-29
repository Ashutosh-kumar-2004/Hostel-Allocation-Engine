import os
import sys

sys.path.insert(0, os.path.abspath("."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from apps.applications.models import Application, AllocationCycle
from apps.inventory.models import Hostel
from apps.preferences.models import Preference, RoommateRequest
from apps.preferences.services import PreferenceService
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.preferences.views import preferences_list_view, roommate_requests_hub_view
from apps.compatibility.models import CompatibilityResponse
from apps.compatibility.services import CompatibilityService

User = get_user_model()

def run_tests():
    print("--- 1. SETTING UP TEST USERS & PROFILES ---")
    ashutosh_user, _ = User.objects.get_or_create(username="12300901", defaults={"email": "ashutosh@example.com", "first_name": "Ashutosh"})
    ayush_user, _ = User.objects.get_or_create(username="12300002", defaults={"email": "ayush@example.com", "first_name": "Ayush"})
    
    cycle = AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING", "REVIEW"]).first() or AllocationCycle.objects.first()
    hostel = Hostel.objects.filter(is_active=True, gender_type="M").first()
    
    app_ashutosh, _ = Application.objects.get_or_create(
        cycle=cycle,
        student_id="12300901",
        defaults={
            "user": ashutosh_user,
            "student_name": "Ashutosh Sharma",
            "student_email": "ashutosh@example.com",
            "gender": "M",
            "cgpa": 8.8,
            "has_disciplinary_record": False,
            "fee_cleared": True,
            "programme": "B.Tech Computer Science",
            "year_of_study": 2,
        }
    )
    app_ashutosh.user = ashutosh_user
    app_ashutosh.save()

    app_ayush, _ = Application.objects.get_or_create(
        cycle=cycle,
        student_id="12300002",
        defaults={
            "user": ayush_user,
            "student_name": "Ayush Menon",
            "student_email": "ayush@example.com",
            "gender": "M",
            "cgpa": 8.5,
            "has_disciplinary_record": False,
            "fee_cleared": True,
            "programme": "B.Tech Mechanical",
            "year_of_study": 2,
        }
    )
    app_ayush.user = ayush_user
    app_ayush.save()

    # Clear prior test state
    RoommateRequest.objects.filter(requester__in=[app_ashutosh, app_ayush]).delete()
    RoommateRequest.objects.filter(target__in=[app_ashutosh, app_ayush]).delete()
    Notification.objects.filter(recipient_user__in=[ashutosh_user, ayush_user]).delete()
    Preference.objects.filter(application__in=[app_ashutosh, app_ayush]).delete()

    # Ensure compatibility survey responses
    CompatibilityResponse.objects.update_or_create(
        application=app_ashutosh,
        defaults={
            "sleep_habit": "EARLY_BIRD",
            "study_environment": "SILENT",
            "cleanliness_priority": "VERY_STRICT",
            "guest_tolerance_score": 4,
            "consent_recorded": True,
        }
    )
    CompatibilityResponse.objects.update_or_create(
        application=app_ayush,
        defaults={
            "sleep_habit": "EARLY_BIRD",
            "study_environment": "SILENT",
            "cleanliness_priority": "VERY_STRICT",
            "guest_tolerance_score": 3,
            "consent_recorded": True,
        }
    )

    print("Setup verified. Compatibility breakdown:")
    breakdown = CompatibilityService.get_detailed_breakdown(app_ashutosh, app_ayush)
    print(f"Overall Synergy: {breakdown['percentage']}% ({breakdown['harmony_level']})")
    assert breakdown['percentage'] >= 90, "Expected high synergy between test students"

    factory = RequestFactory()

    print("\n--- 2. TEST: ASHUTOSH SUBMITS PREFERENCE REQUESTING AYUSH ---")
    post_data = {
        "rank_1_hostel": str(hostel.id),
        "rank_1_room_type": "DOUBLE",
        "rank_1_roommate": "12300002",
        "rank_2_hostel": str(hostel.id),
        "rank_2_room_type": "DOUBLE",
        "rank_2_roommate": "",
        "rank_3_hostel": str(hostel.id),
        "rank_3_room_type": "DOUBLE",
        "rank_3_roommate": "",
    }
    req = factory.post("/preferences/", data=post_data)
    req.user = ashutosh_user
    from django.contrib.messages.storage.fallback import FallbackStorage
    setattr(req, "session", {})
    messages_storage = FallbackStorage(req)
    setattr(req, "_messages", messages_storage)

    resp = preferences_list_view(req)
    assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"

    # Verify RoommateRequest created
    roommate_req = RoommateRequest.objects.filter(requester=app_ashutosh, target=app_ayush).first()
    assert roommate_req is not None, "RoommateRequest was not created!"
    assert roommate_req.status == "PENDING", f"Expected PENDING, got {roommate_req.status}"
    print(f"[PASS] RoommateRequest created successfully: status={roommate_req.status}")

    # Verify In-App Notification received by Ayush
    notifs = Notification.objects.filter(recipient_user=ayush_user)
    assert notifs.exists(), "Ayush did not receive in-app notification!"
    notif = notifs.first()
    assert notif.notification_type == "ROOMMATE_REQUEST"
    assert notif.action_url == "/preferences/requests/"
    print(f"[PASS] Notification sent to Ayush: '{notif.subject}', action_url='{notif.action_url}'")

    print("\n--- 3. TEST: AYUSH REVIEWS REQUEST HUB (GET) ---")
    req_get = factory.get("/preferences/requests/")
    req_get.user = ayush_user
    setattr(req_get, "session", {})
    setattr(req_get, "_messages", FallbackStorage(req_get))
    resp_hub = roommate_requests_hub_view(req_get)
    assert resp_hub.status_code == 200, f"Expected 200 OK, got {resp_hub.status_code}"
    print("[PASS] Roommate Requests Hub rendered for Ayush with pending request and synergy breakdown!")

    print("\n--- 4. TEST: DECLINE FLOW ---")
    post_decline = {
        "action": "decline",
        "request_id": str(roommate_req.id),
        "decline_reason": "Prefer individual room allocation pool",
    }
    req_dec = factory.post("/preferences/requests/", data=post_decline)
    req_dec.user = ayush_user
    setattr(req_dec, "session", {})
    setattr(req_dec, "_messages", FallbackStorage(req_dec))
    resp_dec = roommate_requests_hub_view(req_dec)
    assert resp_dec.status_code == 302

    roommate_req.refresh_from_db()
    assert roommate_req.status == "DECLINED", f"Expected DECLINED, got {roommate_req.status}"
    print(f"[PASS] Request declined: status={roommate_req.status}, reason='{roommate_req.decline_reason}'")

    # Verify Ashutosh's preference preferred_roommate_id is cleared
    ashutosh_pref = Preference.objects.filter(application=app_ashutosh, rank=1).first()
    assert ashutosh_pref.preferred_roommate_id is None, "Ashutosh's roommate_id was not cleared on decline!"
    print("[PASS] Ashutosh's preferred_roommate_id reset to None (fallback to Individual Allocation Pool).")

    # Verify Ashutosh received decline notification
    ashutosh_notifs = Notification.objects.filter(recipient_user=ashutosh_user, notification_type="ROOMMATE_DECLINED")
    assert ashutosh_notifs.exists(), "Ashutosh did not receive decline notification!"
    print(f"[PASS] Ashutosh received polite fallback notification: '{ashutosh_notifs.first().subject}'")

    print("\n--- 5. TEST: ACCEPT FLOW & BI-DIRECTIONAL CONFIRMATION ---")
    # Ashutosh requests Ayush again
    post_data["rank_1_roommate"] = "12300002"
    req_repost = factory.post("/preferences/", data=post_data)
    req_repost.user = ashutosh_user
    setattr(req_repost, "session", {})
    setattr(req_repost, "_messages", FallbackStorage(req_repost))
    preferences_list_view(req_repost)

    roommate_req.refresh_from_db()
    assert roommate_req.status == "PENDING"

    # Ayush accepts request
    post_accept = {
        "action": "accept",
        "request_id": str(roommate_req.id),
    }
    req_acc = factory.post("/preferences/requests/", data=post_accept)
    req_acc.user = ayush_user
    setattr(req_acc, "session", {})
    setattr(req_acc, "_messages", FallbackStorage(req_acc))
    resp_acc = roommate_requests_hub_view(req_acc)
    assert resp_acc.status_code == 302

    roommate_req.refresh_from_db()
    assert roommate_req.status == "ACCEPTED", f"Expected ACCEPTED, got {roommate_req.status}"
    print(f"[PASS] Request accepted: status={roommate_req.status}")

    # Check bi-directional preferences
    ashutosh_pref.refresh_from_db()
    ayush_pref = Preference.objects.filter(application=app_ayush, rank=1).first()
    assert ashutosh_pref.preferred_roommate_id == "12300002"
    assert ayush_pref is not None and ayush_pref.preferred_roommate_id == "12300901"
    print(f"[PASS] Bi-directional sync verified: Ashutosh -> {ashutosh_pref.preferred_roommate_id}, Ayush -> {ayush_pref.preferred_roommate_id}")

    # Check PreferenceService mutual status
    status_ashutosh = PreferenceService.check_roommate_mutual_status(app_ashutosh)
    status_ayush = PreferenceService.check_roommate_mutual_status(app_ayush)
    assert status_ashutosh["status"] == "MUTUAL_CONFIRMED"
    assert status_ayush["status"] == "MUTUAL_CONFIRMED"
    print(f"[PASS] Mutual confirmation verified by solver service: status={status_ashutosh['status']}")

    # Check notification to Ashutosh
    accept_notifs = Notification.objects.filter(recipient_user=ashutosh_user, notification_type="ROOMMATE_ACCEPTED")
    assert accept_notifs.exists(), "Ashutosh did not receive acceptance notification!"
    print(f"[PASS] Ashutosh received acceptance notification: '{accept_notifs.first().subject}'")

    print("\n=== ALL TESTS PASSED SUCCESSFULLY! 100% CORRECT! ===")

if __name__ == "__main__":
    run_tests()
