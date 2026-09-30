from apps.inventory.models import WardenHostelAssignment
from apps.applications.models import Application

def user_roles(request):
    """
    Context processor to provide role flags across all templates:
    - is_admin: True if superuser or staff
    - is_warden: True if user has a WardenHostelAssignment or warden email
    - is_student: True if user is linked to an Application or has student registration number
    - current_role_name: Clean display title for current active role
    - warden_hostel: The assigned Hostel if user is a Warden
    - student_application: The Application record if user is a Student
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {
            "is_admin": False,
            "is_warden": False,
            "is_student": False,
            "is_guest": True,
            "current_role_name": "Visitor",
            "warden_hostel": None,
            "student_application": None,
        }

    user = request.user
    
    # Check if warden (via assignment or email)
    warden_assignment = WardenHostelAssignment.objects.filter(
        user=user
    ).select_related("hostel").first()
    
    if not warden_assignment and user.email:
        warden_assignment = WardenHostelAssignment.objects.filter(
            warden_email__iexact=user.email
        ).select_related("hostel").first()

    is_warden = bool(warden_assignment or "warden" in user.username.lower() or "warden" in (user.email or "").lower())
    
    # Superuser or non-warden staff is system administrator
    is_admin = bool(user.is_superuser or (user.is_staff and not is_warden))
    
    # Check if student (linked application or registration format)
    student_app = getattr(user, "student_application", None)
    if not student_app:
        student_app = Application.objects.filter(student_id=user.username).first()
        if not student_app and user.email:
            student_app = Application.objects.filter(student_email__iexact=user.email).first()

    # A user is student if they have an application or username starts with 123
    is_student = bool(student_app or (user.username.startswith("123") and not is_warden and not is_admin))

    # Determine primary display role name
    if is_admin:
        role_name = "System Administrator"
    elif is_warden:
        if warden_assignment:
            role_name = f"Warden ({warden_assignment.hostel.name})"
        else:
            role_name = "Hostel Warden"
    elif is_student:
        role_name = f"Student ({user.username})"
    else:
        role_name = "Authenticated User"

    # Determine student gender and waitlist badge if available
    student_gender = None
    user_waitlist_badge = None
    if student_app:
        student_gender = student_app.gender
        try:
            from apps.waitlist.models import WaitlistEntry
            w_entry = WaitlistEntry.objects.filter(application=student_app).order_by("-created_at").first()
            if w_entry:
                if w_entry.status == "OFFERED":
                    user_waitlist_badge = "Bed Offered!"
                elif w_entry.status == "ACTIVE":
                    user_waitlist_badge = f"#{w_entry.priority_order}"
        except Exception:
            pass

    active_waitlist_count = 0
    pending_checkins_count = 0
    pending_reviews_count = 0
    if is_warden or is_admin:
        try:
            from apps.waitlist.models import WaitlistEntry
            active_waitlist_count = WaitlistEntry.objects.filter(status="ACTIVE").count()
        except Exception:
            pass

        try:
            from apps.publication.models import AllocationLetter
            pub_letters = AllocationLetter.objects.filter(is_checked_in=False, assignment__draft__status="PUBLISHED")
            if is_warden and not user.is_superuser and warden_assignment:
                pub_letters = pub_letters.filter(assignment__bed__room__block__hostel=warden_assignment.hostel)
            pending_checkins_count = pub_letters.count()
        except Exception:
            pass

        try:
            from apps.allocation.models import AllocationDraft
            pending_reviews_count = AllocationDraft.objects.filter(status__in=["COMPLETED", "REVIEWED"]).count()
        except Exception:
            pass

    user_has_allotment = False
    if is_student and student_app:
        try:
            from apps.allocation.models import AllocationAssignment
            user_has_allotment = AllocationAssignment.objects.filter(
                application=student_app,
                draft__status="PUBLISHED"
            ).exists()
        except Exception:
            pass

    return {
        "is_admin": is_admin,
        "is_warden": is_warden,
        "is_student": is_student,
        "is_guest": False,
        "current_role_name": role_name,
        "warden_hostel": warden_assignment.hostel if warden_assignment else None,
        "student_application": student_app,
        "student_gender": student_gender,
        "user_waitlist_badge": user_waitlist_badge,
        "active_waitlist_count": active_waitlist_count,
        "pending_checkins_count": pending_checkins_count,
        "pending_reviews_count": pending_reviews_count,
        "user_has_allotment": user_has_allotment,
    }


