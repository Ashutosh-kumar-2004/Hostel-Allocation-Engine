import os
import sys
import django

sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test import Client

def extract_aside(html: str) -> str:
    start = html.find("<aside")
    end = html.find("</aside>")
    if start != -1 and end != -1:
        return html[start:end+8]
    return ""

def test_roles():
    c = Client()
    
    # 1. GUEST / VISITOR
    c.logout()
    resp_guest = c.get("/")
    assert resp_guest.status_code == 200
    aside_guest = extract_aside(resp_guest.content.decode())
    assert "Hostel &amp; Room Explorer" in aside_guest
    assert "Register New Student" in aside_guest
    assert "Sign In" in aside_guest
    assert "Warden Console" not in aside_guest
    assert "Admin Console" not in aside_guest
    assert "Draft Review" not in aside_guest
    print("[PASS] Guest Sidebar: Clean visitor links only.")

    # 2. STUDENT (12300901)
    c.logout()
    logged_in = c.login(username="12300901", password="Student@123")
    assert logged_in, "Failed to login as student 12300901"
    resp_stu = c.get("/")
    assert resp_stu.status_code == 200
    aside_stu = extract_aside(resp_stu.content.decode())
    
    # Positive checks for Student
    assert "Student Portal" in aside_stu
    assert "Student Dashboard" in aside_stu
    assert "My Application (M2)" in aside_stu
    assert "Ranked Preferences (M4)" in aside_stu
    assert "Roommate Requests" in aside_stu
    assert "Lifestyle Questionnaire (M5)" in aside_stu
    assert "My Allotment &amp; Letter (M9)" in aside_stu
    assert "My Waitlist Status (M8)" in aside_stu
    
    # Negative checks for Student (Must NOT see Warden or Admin stuff!)
    assert "Warden Portal" not in aside_stu
    assert "Warden Console" not in aside_stu
    assert "Admin Console" not in aside_stu
    assert "Warden Assignments" not in aside_stu
    assert "Draft Review &amp; Sign-off" not in aside_stu
    assert "Engine Runs &amp; Drafts" not in aside_stu
    assert "Django Superuser Admin" not in aside_stu
    print("[PASS] Student Sidebar: Strict student-only features.")

    # 3. WARDEN (rajesh.warden)
    c.logout()
    logged_in = c.login(username="rajesh.warden", password="warden123")
    assert logged_in, "Failed to login as warden rajesh.warden"
    resp_w = c.get("/")
    assert resp_w.status_code == 200
    aside_w = extract_aside(resp_w.content.decode())
    
    # Positive checks for Warden
    assert "Warden Portal" in aside_w
    assert "Warden Console" in aside_w
    assert "Interactive Bed Map (M1)" in aside_w
    assert "Check-In &amp; Keys (M9)" in aside_w
    assert "Draft Review &amp; Sign-off (M7)" in aside_w
    assert "Waiting List (M8)" in aside_w
    assert "What-if Simulation" in aside_w
    
    # Negative checks for Warden (Must NOT see Student intake/questionnaires or Admin system tools!)
    assert "Student Portal" not in aside_w
    assert "My Application (M2)" not in aside_w
    assert "Lifestyle Questionnaire (M5)" not in aside_w
    assert "Warden Assignments" not in aside_w
    assert "Engine Runs &amp; Drafts" not in aside_w
    assert "Django Superuser Admin" not in aside_w
    print("[PASS] Warden Sidebar: Strict warden-only features scoped to hostel.")

    # 4. SYSTEM ADMINISTRATOR (admin)
    c.logout()
    logged_in = c.login(username="admin", password="admin123")
    assert logged_in, "Failed to login as admin"
    resp_a = c.get("/")
    assert resp_a.status_code == 200
    aside_a = extract_aside(resp_a.content.decode())
    
    # Positive checks for Admin
    assert "Admin Console" in aside_a
    assert "Admin Dashboard" in aside_a
    assert "Flowcharts &amp; ERD" in aside_a
    assert "Engine Runs &amp; Drafts (M6)" in aside_a
    assert "What-if Simulation Engine" in aside_a
    assert "Cycles &amp; Applicants (M2)" in aside_a
    assert "Warden Review Gate (M7)" in aside_a
    assert "Publications &amp; Keys (M9)" in aside_a
    assert "Waitlist Queue (M8)" in aside_a
    assert "Hostel Master Registry" in aside_a
    assert "Interactive Bed Map (All)" in aside_a
    assert "Warden Assignments" in aside_a
    assert "Eligibility Rules (M3)" in aside_a
    assert "Audit Trail Log" in aside_a
    assert "Django Superuser Admin" in aside_a
    
    # Negative checks for Admin (Must NOT see Student personal application links!)
    assert "Student Portal" not in aside_a
    assert "My Application (M2)" not in aside_a
    assert "My Allotment &amp; Letter (M9)" not in aside_a
    assert "Roommate Requests" not in aside_a
    print("[PASS] Admin Sidebar: Strict administrator-level university operations.")

    print("\n" + "=" * 80)
    print("ALL 4 USER-LEVEL SIDEBAR ROLES VALIDATED COMPLETELY & ACCURATELY!")
    print("=" * 80)

if __name__ == "__main__":
    test_roles()
