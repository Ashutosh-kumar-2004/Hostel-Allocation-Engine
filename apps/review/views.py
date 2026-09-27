from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.decorators import warden_or_admin_required
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.review.models import WardenApproval, Override
from apps.review.services import ReviewService
from apps.publication.services import PublicationService
from apps.inventory.models import WardenHostelAssignment

@login_required
@warden_or_admin_required
def review_dashboard_view(request):
    """
    Overview of drafts awaiting warden review and published batches.
    Displays scoped metrics and direct links to inspect drafts.
    """
    drafts_for_review = AllocationDraft.objects.filter(
        status__in=["COMPLETED", "REVIEWED", "IN_PROGRESS"]
    ).select_related("cycle").order_by("-created_at")

    published_drafts = AllocationDraft.objects.filter(
        status="PUBLISHED"
    ).select_related("cycle").order_by("-created_at")

    warden_assign = WardenHostelAssignment.objects.filter(user=request.user).select_related("hostel").first()
    is_scoped_warden = warden_assign is not None and not (request.user.is_superuser or request.user.is_staff)
    scoped_hostel = warden_assign.hostel if is_scoped_warden else None

    # Calculate pending overrides count
    total_overrides = Override.objects.count()

    context = {
        "drafts": drafts_for_review,
        "published_drafts": published_drafts,
        "is_scoped_warden": is_scoped_warden,
        "scoped_hostel": scoped_hostel,
        "total_overrides": total_overrides,
    }
    return render(request, "review/dashboard.html", context)

@login_required
@warden_or_admin_required
def draft_review_view(request, draft_id):
    """
    Primary M7 Warden Review & Manual Reallocation Workspace.
    - Scoped strictly to the Warden's assigned hostel (if warden), or full campus (if admin).
    - Lists all bed assignments with student info, room type, mutual roommate tags, and compatibility.
    - Provides vacant beds list for manual override.
    - Provides resident swap action with instant constraint check.
    - Allows Warden sign-off & approval.
    """
    draft = get_object_or_404(AllocationDraft.objects.select_related("cycle"), id=draft_id)
    query = request.GET.get("q", "").strip()
    hostel_filter = request.GET.get("hostel", "").strip() or None
    floor_filter = request.GET.get("floor", "").strip() or None

    review_ctx = ReviewService.get_review_context_for_draft(
        draft=draft,
        user=request.user,
        query=query,
        hostel_filter=hostel_filter,
        floor_filter=floor_filter
    )
    return render(request, "review/draft_review.html", review_ctx)

@login_required
@warden_or_admin_required
def apply_override_view(request, draft_id):
    """
    POST endpoint: Manually reassign a resident to an unoccupied bed.
    Requires mandatory justification reason.
    """
    if request.method != "POST":
        return redirect("review:draft_review", draft_id=draft_id)

    draft = get_object_or_404(AllocationDraft, id=draft_id)
    assignment_id = request.POST.get("assignment_id")
    new_bed_id = request.POST.get("new_bed_id")
    reason = request.POST.get("reason", "").strip()

    warden_assign = WardenHostelAssignment.objects.filter(user=request.user).first()
    scoped_hostel_id = str(warden_assign.hostel_id) if warden_assign and not (request.user.is_superuser or request.user.is_staff) else None

    warden_id = str(request.user.id)
    warden_email = request.user.email or f"{request.user.username}@university.edu"

    try:
        override = ReviewService.apply_override(
            assignment_id=assignment_id,
            new_bed_id=new_bed_id,
            warden_id=warden_id,
            warden_email=warden_email,
            reason=reason,
            warden_hostel_id=scoped_hostel_id
        )
        messages.success(
            request,
            f"Override applied successfully! Student {override.assignment.application.student_name} reassigned to Bed {override.new_bed.bed_identifier} (Room {override.new_bed.room.room_number})."
        )
    except Exception as e:
        messages.error(request, f"Reassignment failed: {str(e)}")

    return redirect("review:draft_review", draft_id=draft_id)

@login_required
@warden_or_admin_required
def swap_residents_view(request, draft_id):
    """
    POST endpoint: Atomically swap beds of two students within the draft.
    Requires mandatory justification reason and verifies cross-constraints.
    """
    if request.method != "POST":
        return redirect("review:draft_review", draft_id=draft_id)

    draft = get_object_or_404(AllocationDraft, id=draft_id)
    assignment_a_id = request.POST.get("assignment_a_id")
    assignment_b_id = request.POST.get("assignment_b_id")
    reason = request.POST.get("reason", "").strip()

    warden_assign = WardenHostelAssignment.objects.filter(user=request.user).first()
    scoped_hostel_id = str(warden_assign.hostel_id) if warden_assign and not (request.user.is_superuser or request.user.is_staff) else None

    warden_id = str(request.user.id)
    warden_email = request.user.email or f"{request.user.username}@university.edu"

    try:
        override_a, override_b = ReviewService.swap_assignments(
            assignment_a_id=assignment_a_id,
            assignment_b_id=assignment_b_id,
            warden_id=warden_id,
            warden_email=warden_email,
            reason=reason,
            warden_hostel_id=scoped_hostel_id
        )
        messages.success(
            request,
            f"Resident swap executed successfully between {override_a.assignment.application.student_name} and {override_b.assignment.application.student_name}."
        )
    except Exception as e:
        messages.error(request, f"Swap failed: {str(e)}")

    return redirect("review:draft_review", draft_id=draft_id)

@login_required
@warden_or_admin_required
def approve_draft_view(request, draft_id):
    """
    POST endpoint: Record Warden Approval sign-off.
    Transitions draft to REVIEWED state.
    """
    if request.method != "POST":
        return redirect("review:draft_review", draft_id=draft_id)

    draft = get_object_or_404(AllocationDraft, id=draft_id)
    comments = request.POST.get("comments", "").strip()
    warden_id = str(request.user.id)
    warden_email = request.user.email or f"{request.user.username}@university.edu"

    try:
        approval = ReviewService.approve_draft(
            draft_id=str(draft.id),
            warden_id=warden_id,
            warden_email=warden_email,
            comments=comments
        )
        messages.success(
            request,
            f"Draft {draft.run_identifier} has been officially approved and signed off by {warden_email}. Draft is now ready for publication!"
        )
    except Exception as e:
        messages.error(request, f"Approval failed: {str(e)}")

    return redirect("review:draft_review", draft_id=draft_id)

@login_required
@warden_or_admin_required
def approve_and_publish_draft_view(request, draft_id):
    """
    POST endpoint: Records approval (if not already recorded) and immediately publishes the draft.
    Transitions draft to PUBLISHED state and generates official Allotment Letters.
    """
    draft = get_object_or_404(AllocationDraft, id=draft_id)
    if request.method != "POST":
        return redirect("review:draft_review", draft_id=draft_id)

    comments = request.POST.get("comments", "Approved following warden room audit.")
    user = request.user
    warden_id = str(user.id)
    warden_email = user.email or f"{user.username}@university.edu"

    try:
        # 1. Ensure approval is recorded
        ReviewService.approve_draft(
            draft_id=str(draft.id),
            warden_id=warden_id,
            warden_email=warden_email,
            comments=comments
        )

        # 2. Publish draft via PublicationService
        pub_record = PublicationService.publish_draft(
            draft_id=str(draft.id),
            publisher_id=warden_id,
            publisher_email=warden_email
        )
        messages.success(
            request,
            f"Draft {draft.run_identifier} successfully approved and sealed! Official Allotment Letters have been released to students."
        )
        return redirect("publication:list")
    except Exception as e:
        messages.error(request, f"Failed to publish draft: {str(e)}")
        return redirect("review:draft_review", draft_id=draft_id)

@login_required
@warden_or_admin_required
def overrides_log_view(request, draft_id):
    """
    Audit ledger of all manual overrides and swaps for a draft.
    """
    draft = get_object_or_404(AllocationDraft.objects.select_related("cycle"), id=draft_id)
    overrides = Override.objects.filter(assignment__draft=draft).select_related(
        "assignment", "assignment__application", "previous_bed", "previous_bed__room",
        "previous_bed__room__block__hostel", "new_bed", "new_bed__room", "new_bed__room__block__hostel"
    ).order_by("-created_at")

    return render(request, "review/overrides_log.html", {
        "draft": draft,
        "overrides": overrides
    })
