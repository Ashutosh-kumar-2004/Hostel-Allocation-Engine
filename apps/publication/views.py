from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q
from .models import PublicationRecord, AllocationLetter
from .services import PublicationService
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.applications.models import Application
from apps.inventory.models import WardenHostelAssignment
from apps.core.decorators import warden_or_admin_required

@login_required
def publications_view(request):
    """
    Role-aware Publication Hub:
    - Students see their official immutable Allotment Letter & certificate (or draft review status).
    - Wardens and Admins see the published cycles audit, seal controls, and hostel-scoped issued letters registry
      with student check-in & physical key handover controls.
    """
    user = request.user
    
    # 1. Determine role flags
    warden_assign = WardenHostelAssignment.objects.filter(user=user).select_related("hostel").first()
    if not warden_assign and user.email:
        warden_assign = WardenHostelAssignment.objects.filter(warden_email__iexact=user.email).first()
    is_warden = bool(warden_assign or "warden" in user.username.lower() or "warden" in (user.email or "").lower())
    is_admin = bool(user.is_superuser or (user.is_staff and not is_warden))
    
    # Student resolution
    student_app = getattr(user, "student_application", None)
    if not student_app:
        student_app = Application.objects.filter(student_id=user.username).first()
        if not student_app and user.email:
            student_app = Application.objects.filter(student_email__iexact=user.email).first()
    
    is_student = bool(student_app or (user.username.startswith("123") and not is_warden and not is_admin))

    # Context containers
    context = {
        "is_admin": is_admin,
        "is_warden": is_warden,
        "is_student": is_student,
        "student_app": student_app,
        "warden_hostel": warden_assign.hostel if warden_assign else None,
    }

    # ================= STUDENT VIEW LOGIC =================
    if is_student and not is_admin and not is_warden:
        student_assignment = None
        student_letter = None
        provisional_assignment = None

        if student_app:
            # Check for officially published assignment first
            student_assignment = AllocationAssignment.objects.filter(
                application=student_app,
                draft__status="PUBLISHED"
            ).select_related(
                "draft", "draft__cycle", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"
            ).first()

            # Cross-verify with real active bed in inventory (in case of approved room transfer)
            from apps.inventory.models import Bed
            active_occupied_bed = Bed.objects.filter(
                occupant_student_id=student_app.student_id,
                status="OCCUPIED"
            ).select_related("room", "room__block", "room__block__hostel").first()

            if student_assignment and active_occupied_bed and student_assignment.bed != active_occupied_bed:
                student_assignment.bed = active_occupied_bed
                student_assignment.save(update_fields=["bed"])

            if student_assignment:
                student_letter = AllocationLetter.objects.filter(assignment=student_assignment).first()
                if not student_letter:
                    # Guarantee letter existence
                    ref = f"AL-{student_assignment.draft.cycle.code}-{student_assignment.bed.room.block.hostel.code}-{student_app.student_id}"
                    import hashlib
                    qr_code = hashlib.sha256(f"{ref}:{student_assignment.id}".encode()).hexdigest()[:16].upper()
                    student_letter, _ = AllocationLetter.objects.get_or_create(
                        assignment=student_assignment,
                        defaults={
                            "document_reference": ref,
                            "qr_verification_code": qr_code,
                            "institution_id": student_assignment.draft.institution_id
                        }
                    )
                elif active_occupied_bed and student_letter.assignment.bed != active_occupied_bed:
                    student_letter.assignment.bed = active_occupied_bed
            else:
                # Check for provisional draft assignment awaiting warden publication
                provisional_assignment = AllocationAssignment.objects.filter(
                    application=student_app
                ).select_related(
                    "draft", "draft__cycle", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"
                ).order_by("-draft__created_at").first()

        context.update({
            "student_assignment": student_assignment,
            "student_letter": student_letter,
            "provisional_assignment": provisional_assignment,
        })
        return render(request, "publication/student_letter_view.html", context)

    # ================= WARDEN / ADMIN VIEW LOGIC =================
    publications = PublicationRecord.objects.select_related("draft", "draft__cycle").all().order_by("-published_at")
    pending_drafts = AllocationDraft.objects.filter(status__in=["COMPLETED", "REVIEWED"]).order_by("-created_at")

    # Letters Query
    letters_qs = AllocationLetter.objects.select_related(
        "assignment",
        "assignment__application",
        "assignment__bed",
        "assignment__bed__room",
        "assignment__bed__room__block",
        "assignment__bed__room__block__hostel",
        "assignment__draft",
        "assignment__draft__cycle"
    ).all().order_by("-issued_at")

    # Scope to warden's hostel if assigned
    if is_warden and not user.is_superuser and warden_assign:
        letters_qs = letters_qs.filter(assignment__bed__room__block__hostel=warden_assign.hostel)

    total_letters_issued = letters_qs.count()
    total_checked_in = letters_qs.filter(is_checked_in=True).count()
    pending_check_in = letters_qs.filter(is_checked_in=False).count()

    # Filter tab
    status_filter = request.GET.get("status", "all").strip().lower()
    if status_filter == "checked_in":
        letters_qs = letters_qs.filter(is_checked_in=True)
    elif status_filter == "pending":
        letters_qs = letters_qs.filter(is_checked_in=False)

    # Search filter
    q = request.GET.get("q", "").strip()
    if q:
        letters_qs = letters_qs.filter(
            Q(document_reference__icontains=q) |
            Q(qr_verification_code__icontains=q) |
            Q(key_number_issued__icontains=q) |
            Q(assignment__application__student_name__icontains=q) |
            Q(assignment__application__student_id__icontains=q) |
            Q(assignment__bed__room__room_number__icontains=q)
        )

    context.update({
        "publications": publications,
        "pending_drafts": pending_drafts,
        "letters": letters_qs[:100],  # increased to 100
        "total_published_cycles": publications.count(),
        "total_letters_issued": total_letters_issued,
        "total_checked_in": total_checked_in,
        "pending_check_in": pending_check_in,
        "pending_drafts_count": pending_drafts.count(),
        "search_query": q,
        "status_filter": status_filter,
    })
    return render(request, "publication/list.html", context)


@login_required
@warden_or_admin_required
def check_in_student_view(request, letter_id):
    """
    POST endpoint: Records student physical arrival, checks in the resident,
    issues a physical key number, and updates Bed inventory to OCCUPIED.
    """
    if request.method != "POST":
        return redirect("publication:list")

    letter = get_object_or_404(
        AllocationLetter.objects.select_related(
            "assignment",
            "assignment__bed",
            "assignment__bed__room",
            "assignment__bed__room__block",
            "assignment__bed__room__block__hostel",
            "assignment__application"
        ),
        id=letter_id
    )

    # Scoped permission check for wardens
    warden_assign = getattr(request, "warden_assignment", None)
    if not request.user.is_superuser and warden_assign:
        letter_hostel = (
            letter.assignment.bed.room.block.hostel
            if letter.assignment.bed and letter.assignment.bed.room and letter.assignment.bed.room.block
            else None
        )
        if letter_hostel and letter_hostel != warden_assign.hostel:
            messages.error(
                request,
                f"Permission Denied: You are assigned to {warden_assign.hostel.name} and cannot manage check-ins for {letter_hostel.name}."
            )
            return redirect("publication:list")

    key_number = request.POST.get("key_number", "").strip()
    remarks = request.POST.get("remarks", "").strip()

    if not key_number:
        messages.error(request, "Error: Key number is mandatory to complete student room check-in.")
        return redirect("publication:list")

    try:
        PublicationService.check_in_student(
            letter_id_or_ref=str(letter.id),
            key_number=key_number,
            verified_by_email=request.user.email or f"{request.user.username}@university.edu",
            verified_by_id=str(request.user.id),
            remarks=remarks
        )
        messages.success(
            request,
            f"Resident {letter.assignment.application.student_name} ({letter.assignment.application.student_id}) checked in successfully. Key #{key_number} issued and bed marked OCCUPIED."
        )
    except Exception as e:
        messages.error(request, f"Check-in failed: {str(e)}")

    return redirect("publication:list")


@login_required
def official_allotment_letter_view(request, document_reference):
    """
    Official Printable / Downloadable Allotment Letter.
    Designed for print / PDF generation with full legal letterhead.
    Accessible to the respective student or Wardens/Admins.
    """
    letter = get_object_or_404(
        AllocationLetter.objects.select_related(
            "assignment",
            "assignment__application",
            "assignment__bed",
            "assignment__bed__room",
            "assignment__bed__room__block",
            "assignment__bed__room__block__hostel",
            "assignment__draft",
            "assignment__draft__cycle"
        ),
        document_reference=document_reference
    )

    # Security check: If student, ensure they only access their own letter
    user = request.user
    is_staff = user.is_staff or user.is_superuser or "warden" in user.username.lower() or "warden" in (user.email or "").lower()
    if not is_staff:
        # Check student ID or email match
        app = letter.assignment.application
        if user.username != app.student_id and user.email != app.student_email:
            messages.error(request, "Access restricted: You may only view your own official allotment letter.")
            return redirect("publication:list")

    return render(request, "publication/letter_document.html", {"letter": letter})


def verify_document_view(request, document_reference):
    """
    Publicly or institutionally accessible verification page.
    Can be loaded directly or via mobile QR code scan.
    """
    verification = PublicationService.verify_letter(document_reference)
    
    if request.headers.get("Accept") == "application/json" or request.GET.get("format") == "json":
        return JsonResponse(verification)

    return render(request, "publication/verify_document.html", {"v": verification, "ref": document_reference})
