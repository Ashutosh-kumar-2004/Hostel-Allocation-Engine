import os
import sys

sys.path.insert(0, os.path.abspath("."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()

from django.contrib.auth import get_user_model
from apps.applications.models import Application, AllocationCycle
from apps.inventory.models import Hostel
from apps.preferences.models import Preference, RoommateRequest
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.compatibility.models import CompatibilityResponse

User = get_user_model()

ashutosh_user = User.objects.get(username="12300901")
ayush_user = User.objects.get(username="12300002")

# Set password for Ayush so we can log in if needed, or check session
ayush_user.set_password("Student@123")
ayush_user.save()
ashutosh_user.set_password("Student@123")
ashutosh_user.save()

cycle = AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING", "REVIEW"]).first() or AllocationCycle.objects.first()
hostel = Hostel.objects.filter(is_active=True, gender_type="M").first()

app_ashutosh = Application.objects.get(cycle=cycle, student_id="12300901")
app_ayush = Application.objects.get(cycle=cycle, student_id="12300002")

# Ashutosh has selected Ayush
Preference.objects.update_or_create(
    application=app_ashutosh,
    rank=1,
    defaults={
        "preferred_hostel": hostel,
        "preferred_room_type": "DOUBLE",
        "preferred_roommate_id": "12300002",
        "institution_id": "inst_default"
    }
)

# Ayush has selected hostel but hasn't accepted yet
Preference.objects.update_or_create(
    application=app_ayush,
    rank=1,
    defaults={
        "preferred_hostel": hostel,
        "preferred_room_type": "DOUBLE",
        "preferred_roommate_id": None,
        "institution_id": "inst_default"
    }
)

# Create pending RoommateRequest
rr, _ = RoommateRequest.objects.update_or_create(
    requester=app_ashutosh,
    target=app_ayush,
    defaults={
        "status": "PENDING",
        "institution_id": "inst_default"
    }
)

# Notification for Ayush
Notification.objects.filter(recipient_user=ayush_user).delete()
NotificationService.send_in_app(
    recipient_user=ayush_user,
    subject=f"Roommate Request from {app_ashutosh.student_name} ({app_ashutosh.student_id})",
    body=f"{app_ashutosh.student_name} has requested you as a mutual roommate for {cycle.name}. View their profile, lifestyle synergy, and residency record to confirm.",
    notification_type="ROOMMATE_REQUEST",
    action_url="/preferences/requests/",
    action_label="Review Request & Profile",
    institution_id="inst_default"
)

print("Demo state initialized: Ayush (12300002) has 1 unread notification and 1 pending roommate request from Ashutosh (12300901). Password: Student@123")
