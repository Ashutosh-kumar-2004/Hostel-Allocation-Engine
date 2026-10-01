import os
import sys
import django

sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from apps.allocation.models import AllocationDraft, AllocationAssignment

User = get_user_model()

def test_views():
    client = Client(SERVER_NAME="localhost")

    # 1. Login as admin
    logged_in = client.login(username="admin", password="admin123")
    print("Admin login status:", logged_in)
    assert logged_in, "Failed to login as admin"

    # 2. Test Draft List View
    print("\n--- Testing Draft List View (/allocation/drafts/) ---")
    resp = client.get("/allocation/drafts/")
    print(f"Status Code: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    content_str = resp.content.decode("utf-8")
    assert "Allocation Engine" in content_str or "Allocation Drafts" in content_str
    print("Draft list view rendered successfully!")

    # 3. Test Draft Detail View
    latest_draft = AllocationDraft.objects.latest("created_at")
    print(f"\n--- Testing Draft Detail View (/allocation/drafts/{latest_draft.id}/) ---")
    resp = client.get(f"/allocation/drafts/{latest_draft.id}/")
    print(f"Status Code: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    content_detail = resp.content.decode("utf-8")
    assert latest_draft.run_identifier in content_detail
    assert "Roommate Synergy" in content_detail or "Mutual Pairs" in content_detail
    print("Rendered assignments in draft detail view!")

    # Test filtering by search query "Ashutosh"
    resp_search = client.get(f"/allocation/drafts/{latest_draft.id}/?q=Ashutosh")
    assert resp_search.status_code == 200
    search_content = resp_search.content.decode("utf-8")
    assert "Ashutosh Kumar Yadav" in search_content
    print("Search query 'Ashutosh' correctly found Ashutosh Kumar Yadav in filtered table!")

    # 4. Test Student Explanation View
    ashutosh_assign = AllocationAssignment.objects.filter(draft=latest_draft, application__student_id="12300901").first()
    assert ashutosh_assign is not None, "Ashutosh assignment not found"
    print(f"\n--- Testing Student Explanation View (/allocation/explanation/{ashutosh_assign.id}/) ---")
    resp_expl = client.get(f"/allocation/explanation/{ashutosh_assign.id}/")
    print(f"Status Code: {resp_expl.status_code}")
    assert resp_expl.status_code == 200, f"Expected 200, got {resp_expl.status_code}"
    assert "Ashutosh Kumar Yadav" in resp_expl.content.decode("utf-8")
    assert "Co-allocated with verified mutual roommate" in resp_expl.content.decode("utf-8")
    print("Explanation view rendered successfully with full transparency breakdown!")

    # 5. Test Trigger Allocation POST endpoint (creates another reproducible draft)
    print("\n--- Testing Trigger Allocation POST (/allocation/trigger/) ---")
    resp_trigger = client.post("/allocation/trigger/", {
        "cycle_id": str(latest_draft.cycle_id),
        "random_seed": "123",
        "hostel_id": "ALL"
    }, follow=True)
    print(f"Status Code: {resp_trigger.status_code}")
    assert resp_trigger.status_code == 200
    new_draft = AllocationDraft.objects.latest("created_at")
    print(f"New Draft created via view trigger: {new_draft.run_identifier} (Seed: {new_draft.random_seed})")
    assert new_draft.status == "COMPLETED"
    assert new_draft.random_seed == 123

    # 6. Test Student Perspective Login & Transparency
    print("\n--- Testing Student Perspective Login (Ashutosh 12300901) ---")
    client.logout()
    student_logged_in = client.login(username="12300901", password="Student@123")
    print("Student login status:", student_logged_in)
    assert student_logged_in, "Failed to login as student"

    # Student accessing explanation view
    resp_student_expl = client.get(f"/allocation/explanation/{ashutosh_assign.id}/")
    print(f"Student access to explanation status code: {resp_student_expl.status_code}")
    assert resp_student_expl.status_code == 200

    print("\n" + "=" * 60)
    print("ALL M6 VIEWS, PERMISSIONS, AND FLOWS FULLY TESTED & WORKING!")
    print("=" * 60)

if __name__ == "__main__":
    test_views()
