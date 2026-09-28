from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.decorators import warden_or_admin_required
from .models import WaitlistEntry
from .services import WaitlistService
from apps.applications.models import AllocationCycle
from apps.inventory.models import Bed, Hostel, WardenHostelAssignment
from apps.allocation.models import AllocationAssignment

def waitlist_view(request):
    """
    Primary Queue Hub for Wardens & Administrators.
    Displays active waitlist queue, bed vacancies, and auto-promotion trigger.
    """
    cycles = AllocationCycle.objects.all().order_by("-application_start")
    cycle_id = request.GET.get("cycle_id")
    selected_cycle = (
        AllocationCycle.objects.filter(id=cycle_id).first()
        if cycle_id
        else AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING"]).first() or cycles.first()
    )

    status_filter = request.GET.get("status", "").strip()

    entries_qs = WaitlistEntry.objects.select_related(
        "cycle", "application", "application__user", "offered_bed",
        "offered_bed__room", "offered_bed__room__block", "offered_bed__room__block__hostel"
    )

    if selected_cycle:
        entries_qs = entries_qs.filter(cycle=selected_cycle)

    if status_filter:
        entries_qs = entries_qs.filter(status=status_filter)

    entries = list(entries_qs.order_by("priority_order", "created_at"))

    # Determine vacant beds count
    assigned_bed_ids = set(
        AllocationAssignment.objects.filter(
            draft__cycle=selected_cycle,
            draft__status__in=["COMPLETED", "REVIEWED", "PUBLISHED"]
        ).values_list("bed_id", flat=True)
    ) if selected_cycle else set()

    currently_offered_bed_ids = set(
        WaitlistEntry.objects.filter(
            cycle=selected_cycle,
            status="OFFERED"
        ).exclude(offered_bed__isnull=True).values_list("offered_bed_id", flat=True)
    ) if selected_cycle else set()

    total_vacant_beds = Bed.objects.filter(status="AVAILABLE").exclude(
        id__in=assigned_bed_ids.union(currently_offered_bed_ids)
    ).count()

    # Active waiting count
    active_count = WaitlistEntry.objects.filter(cycle=selected_cycle, status="ACTIVE").count() if selected_cycle else 0
    offered_count = WaitlistEntry.objects.filter(cycle=selected_cycle, status="OFFERED").count() if selected_cycle else 0
    accepted_count = WaitlistEntry.objects.filter(cycle=selected_cycle, status="ACCEPTED").count() if selected_cycle else 0

    # Vacant beds for manual offer modal (gender-filtered in frontend and backend)
    available_beds = Bed.objects.filter(status="AVAILABLE").exclude(
        id__in=assigned_bed_ids.union(currently_offered_bed_ids)
    ).select_related("room", "room__block", "room__block__hostel").order_by("room__block__hostel__name", "room__room_number")[:150]

    context = {
        "cycles": cycles,
        "selected_cycle": selected_cycle,
        "entries": entries,
        "status_filter": status_filter,
        "total_vacant_beds": total_vacant_beds,
        "active_count": active_count,
        "offered_count": offered_count,
        "accepted_count": accepted_count,
        "available_beds": available_beds,
    }
    return render(request, "waitlist/list.html", context)

@login_required
def student_waitlist_status_view(request):
    """
    Student-facing Waitlist Tracking Portal.
    Allows candidate to check live queue position (#1, #2...) and Accept/Decline bed offers.
    """
    waitlist_info = WaitlistService.get_student_waitlist_info(request.user)
    return render(request, "waitlist/my_status.html", {
        "waitlist_info": waitlist_info,
    })

@login_required
@warden_or_admin_required
def auto_promote_vacancies_view(request):
    """
    POST endpoint: Triggers the dynamic vacancy promotion solver.
    Offers unoccupied beds to the highest-priority eligible candidates in the queue.
    """
    if request.method != "POST":
        return redirect("waitlist:list")

    cycle_id = request.POST.get("cycle_id")
    cycle = (
        get_object_or_404(AllocationCycle, id=cycle_id)
        if cycle_id
        else AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING"]).first() or AllocationCycle.objects.first()
    )

    if not cycle:
        messages.error(request, "No active cycle found.")
        return redirect("waitlist:list")

    warden_assign = WardenHostelAssignment.objects.filter(user=request.user).first()
    scoped_hostel_id = str(warden_assign.hostel_id) if warden_assign and not (request.user.is_superuser or request.user.is_staff) else None

    actor_email = request.user.email or f"{request.user.username}@university.edu"

    try:
        promoted = WaitlistService.auto_promote_vacancies(
            cycle_id=str(cycle.id),
            hostel_id=scoped_hostel_id,
            actor_email=actor_email
        )
        if promoted:
            messages.success(
                request,
                f"Dynamic promotion solver executed! Dispatched {len(promoted)} 48-hour bed offer(s) to top waitlisted candidates."
            )
        else:
            messages.info(
                request,
                "Promotion solver evaluated: No matching vacant beds or no eligible candidates pending in queue."
            )
    except Exception as e:
        messages.error(request, f"Promotion execution failed: {str(e)}")

    return redirect("waitlist:list")

@login_required
def student_respond_offer_view(request, entry_id):
    """
    POST endpoint: Student accepts or declines a bed offer.
    """
    if request.method != "POST":
        return redirect("waitlist:my_status")

    entry = get_object_or_404(WaitlistEntry, id=entry_id)

    # Security check: User must own the application or be admin
    if not (request.user.is_staff or request.user.is_superuser):
        if entry.application.user != request.user:
            messages.error(request, "Permission denied.")
            return redirect("waitlist:my_status")

    action = request.POST.get("action", "").lower()
    actor_email = request.user.email or f"{request.user.username}@university.edu"

    if action == "accept":
        try:
            assignment = WaitlistService.student_accept_offer(
                entry_id=str(entry.id),
                user=request.user,
                actor_email=actor_email
            )
            messages.success(
                request,
                f"🎉 Congratulations! Your bed allotment has been confirmed for Bed {assignment.bed.bed_identifier} in Room {assignment.bed.room.room_number} ({assignment.bed.room.block.hostel.name})."
            )
            return redirect("publication:list")
        except Exception as e:
            messages.error(request, f"Error accepting offer: {str(e)}")
            return redirect("waitlist:my_status")

    elif action == "decline":
        reason = request.POST.get("reason", "").strip()
        try:
            WaitlistService.student_decline_offer(
                entry_id=str(entry.id),
                user=request.user,
                reason=reason,
                actor_email=actor_email
            )
            messages.info(
                request,
                "You have declined the bed offer. The vacant bed has been automatically released to the next student in the queue."
            )
        except Exception as e:
            messages.error(request, f"Error declining offer: {str(e)}")

        return redirect("waitlist:my_status")

    return redirect("waitlist:my_status")

@login_required
@warden_or_admin_required
def manual_offer_bed_view(request, entry_id):
    """
    POST endpoint: Warden specifically offers a selected vacant bed to a waitlisted candidate.
    """
    if request.method != "POST":
        return redirect("waitlist:list")

    bed_id = request.POST.get("bed_id")
    reason = request.POST.get("reason", "").strip()

    try:
        entry = WaitlistService.manual_offer_bed(
            entry_id=str(entry_id),
            bed_id=str(bed_id),
            warden_user=request.user,
            reason=reason
        )
        messages.success(
            request,
            f"Bed offer dispatched to {entry.application.student_name} for Bed {entry.offered_bed.bed_identifier} (Room {entry.offered_bed.room.room_number}). 48-hour acceptance window active."
        )
    except Exception as e:
        messages.error(request, f"Manual offer failed: {str(e)}")

    return redirect("waitlist:list")
