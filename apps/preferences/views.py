from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.utils import timezone
from .models import Preference, RoommateRequest
from .services import PreferenceService
from apps.inventory.models import Hostel, WardenHostelAssignment
from apps.applications.models import Application, AllocationCycle
from apps.notifications.services import NotificationService
from apps.compatibility.services import CompatibilityService
from apps.allocation.models import AllocationAssignment

def preferences_list_view(request):
    """
    Ranked Priority List View:
    1. Students view and submit/update their top 3 ranked choices with strict gender isolation.
    2. Real-time mutual roommate verification (Bi-directional confirmed vs Pending partner).
    3. Wardens/Admins view demand analytics, search/filter submissions, and inspect confirmed mutual pairs.
    """
    warden_assignment = None
    if request.user.is_authenticated:
        warden_assignment = WardenHostelAssignment.objects.filter(
            Q(user=request.user) | Q(warden_email__iexact=request.user.email)
        ).select_related("hostel").first()

    is_warden = bool(warden_assignment or (request.user.is_authenticated and ("warden" in request.user.username.lower() or "warden" in (request.user.email or "").lower())))
    is_admin = bool(request.user.is_authenticated and (request.user.is_superuser or (request.user.is_staff and not is_warden)))
    is_student = bool(request.user.is_authenticated and not is_admin and not is_warden)

    warden_hostel = warden_assignment.hostel if warden_assignment else None
    if is_warden and not warden_hostel:
        # Default assigned hostel for demonstrator warden
        warden_hostel = Hostel.objects.filter(is_active=True).first()

    active_cycle = AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING", "REVIEW"]).first() or AllocationCycle.objects.first()

    # Find student's active application if authenticated
    user_app = None
    if request.user.is_authenticated:
        user_app = getattr(request.user, "student_application", None)
        if not user_app:
            user_app = Application.objects.filter(
                Q(user=request.user) |
                Q(student_id=request.user.username) |
                Q(student_email__iexact=request.user.email)
            ).first()

    # Handle student preference submission / modification (POST)
    if request.method == "POST" and request.user.is_authenticated:
        app_id = request.POST.get("application_id")
        target_app = user_app
        if (is_admin or is_warden) and app_id:
            target_app = Application.objects.filter(id=app_id).first()

        if not target_app:
            messages.error(request, "You must have an active student application before submitting ranked preferences.")
            return redirect("applications:list")

        # Save Rank 1, 2, 3 preferences
        try:
            submitted_roommate_id = None
            for rank_num in (1, 2, 3):
                hostel_id = request.POST.get(f"rank_{rank_num}_hostel")
                room_type = request.POST.get(f"rank_{rank_num}_room_type", "DOUBLE")
                roommate_id = request.POST.get(f"rank_{rank_num}_roommate", "").strip()
                if rank_num == 1 and roommate_id:
                    submitted_roommate_id = roommate_id

                if roommate_id and roommate_id.lower() == (target_app.student_id or "").strip().lower():
                    messages.error(
                        request,
                        f"Self-roommate request invalid: {target_app.student_name} cannot select their own Student ID ({target_app.student_id}) as a roommate. Roommate co-allocation requires another candidate."
                    )
                    return redirect("preferences:list")

                if hostel_id:
                    hostel_obj = Hostel.objects.filter(id=hostel_id, is_active=True).first()
                    if hostel_obj:
                        # Gender isolation policy check
                        is_target_male = target_app.gender in ("M", "MALE")
                        compat_hostels = ["M", "C"] if is_target_male else ["W", "F", "C"]
                        if hostel_obj.gender_type not in compat_hostels:
                            messages.error(
                                request,
                                f"Gender policy mismatch: {hostel_obj.name} is designated for {hostel_obj.get_gender_type_display()} residents, but {target_app.student_name} is registered as {target_app.get_gender_display()}."
                            )
                            return redirect("preferences:list")

                        Preference.objects.update_or_create(
                            application=target_app,
                            rank=rank_num,
                            defaults={
                                "preferred_hostel": hostel_obj,
                                "preferred_room_type": room_type,
                                "preferred_roommate_id": roommate_id or None,
                                "institution_id": target_app.institution_id or "inst_default"
                            }
                        )

            # Sync RoommateRequest lifecycle & dispatch notification
            if submitted_roommate_id:
                candidate_app = Application.objects.filter(cycle=target_app.cycle, student_id__iexact=submitted_roommate_id).first()
                if candidate_app and candidate_app.id != target_app.id and candidate_app.gender == target_app.gender:
                    # Check if candidate requested target_app back
                    reverse_pref = Preference.objects.filter(application=candidate_app, preferred_roommate_id__iexact=target_app.student_id).exists()
                    status_val = "ACCEPTED" if reverse_pref else "PENDING"

                    roommate_req, created = RoommateRequest.objects.get_or_create(
                        requester=target_app,
                        target=candidate_app,
                        defaults={
                            "status": status_val,
                            "institution_id": target_app.institution_id or "inst_default"
                        }
                    )
                    if not created and roommate_req.status != status_val:
                        roommate_req.status = status_val
                        roommate_req.responded_at = timezone.now() if status_val == "ACCEPTED" else None
                        roommate_req.decline_reason = ""
                        roommate_req.save()

                    if status_val == "PENDING" and candidate_app.user:
                        NotificationService.send_in_app(
                            recipient_user=candidate_app.user,
                            subject=f"Roommate Request from {target_app.student_name} ({target_app.student_id})",
                            body=f"{target_app.student_name} has requested you as a mutual roommate. View their profile, lifestyle synergy, and residency record to confirm.",
                            notification_type="ROOMMATE_REQUEST",
                            action_url="/preferences/requests/",
                            action_label="Review Request & Profile",
                            institution_id=target_app.institution_id or "inst_default"
                        )
                    elif status_val == "ACCEPTED":
                        RoommateRequest.objects.filter(requester=candidate_app, target=target_app).update(
                            status="ACCEPTED",
                            responded_at=timezone.now()
                        )
                        if candidate_app.user:
                            NotificationService.send_in_app(
                                recipient_user=candidate_app.user,
                                subject=f"Mutual Roommate Confirmed: {target_app.student_name}",
                                body=f"Your mutual roommate request with {target_app.student_name} ({target_app.student_id}) is now fully verified and locked!",
                                notification_type="ROOMMATE_ACCEPTED",
                                action_url="/preferences/requests/",
                                action_label="View Confirmed Pair",
                                institution_id=target_app.institution_id or "inst_default"
                            )
            else:
                # Cancel any pending requests if user cleared their roommate choice
                RoommateRequest.objects.filter(requester=target_app, status="PENDING").update(
                    status="CANCELLED",
                    responded_at=timezone.now(),
                    decline_reason="Cancelled by requester."
                )

            messages.success(request, f"Ranked preferences saved successfully for {target_app.student_name}!")
        except Exception as e:
            messages.error(request, f"Error saving preferences: {str(e)}")
        return redirect("preferences:list")

    # Base query for table scoped by role
    query = request.GET.get("q", "").strip()
    hostel_filter = request.GET.get("hostel", "").strip()
    room_filter = request.GET.get("room_type", "").strip()
    rank_filter = request.GET.get("rank", "").strip()

    scoped_hostel_id = None
    if is_admin:
        # Admin sees campus-wide submissions
        qs = Preference.objects.select_related("application", "preferred_hostel", "application__cycle").all()
    elif is_warden:
        # Warden only sees submissions choosing their assigned hostel
        scoped_hostel_id = warden_hostel.id if warden_hostel else None
        qs = Preference.objects.filter(preferred_hostel=warden_hostel).select_related("application", "preferred_hostel", "application__cycle") if warden_hostel else Preference.objects.none()
    else:
        # Student strictly sees only their own application choices
        if user_app:
            qs = Preference.objects.filter(application=user_app).select_related("application", "preferred_hostel", "application__cycle")
        else:
            qs = Preference.objects.none()

    if query:
        qs = qs.filter(
            Q(application__student_name__icontains=query) |
            Q(application__student_id__icontains=query) |
            Q(preferred_roommate_id__icontains=query)
        )

    if hostel_filter and is_admin:
        qs = qs.filter(preferred_hostel_id=hostel_filter)

    if room_filter:
        qs = qs.filter(preferred_room_type=room_filter)

    if rank_filter:
        try:
            qs = qs.filter(rank=int(rank_filter))
        except ValueError:
            pass

    preferences = list(qs.order_by("application__student_name", "rank")[:120])

    # Annotate mutual roommate request info on each preference
    for pref in preferences:
        if pref.preferred_roommate_id:
            pref.mutual_info = PreferenceService.check_roommate_mutual_status(pref.application)
        else:
            pref.mutual_info = {"status": "NONE", "label": "None specified"}

    # Available hostels filtered by user's gender for intake safety
    if user_app:
        is_user_male = user_app.gender in ("M", "MALE")
        compat_hostels = ["M", "C"] if is_user_male else ["W", "F", "C"]
        available_hostels = Hostel.objects.filter(is_active=True, gender_type__in=compat_hostels).order_by("name")
    elif is_warden and warden_hostel:
        available_hostels = Hostel.objects.filter(id=warden_hostel.id)
    else:
        available_hostels = Hostel.objects.filter(is_active=True).order_by("name")

    all_hostels = Hostel.objects.filter(is_active=True).order_by("name")

    # User's existing preferences mapped by rank
    user_prefs_by_rank = {}
    user_mutual_status = None
    if user_app:
        for p in Preference.objects.filter(application=user_app):
            user_prefs_by_rank[p.rank] = p
        user_mutual_status = PreferenceService.check_roommate_mutual_status(user_app)

    # Scoped analytics and confirmed pairs (Only for Admin & Warden)
    if is_admin or is_warden:
        confirmed_pairs = PreferenceService.get_confirmed_mutual_pairs(
            cycle_id=active_cycle.id if active_cycle else None,
            hostel_id=scoped_hostel_id
        )
        demand_analytics = PreferenceService.get_demand_analytics(
            cycle_id=active_cycle.id if active_cycle else None,
            hostel_id=scoped_hostel_id
        )
    else:
        confirmed_pairs = []
        demand_analytics = None

    # Stats cards scoped to role
    if is_admin:
        scoped_prefs = Preference.objects.all()
        total_applicants = Application.objects.count()
        with_roommate_req = scoped_prefs.exclude(preferred_roommate_id__isnull=True).exclude(preferred_roommate_id="").values("application").distinct().count()
    elif is_warden and warden_hostel:
        scoped_prefs = Preference.objects.filter(preferred_hostel=warden_hostel)
        total_applicants = scoped_prefs.values("application").distinct().count()
        with_roommate_req = scoped_prefs.exclude(preferred_roommate_id__isnull=True).exclude(preferred_roommate_id="").values("application").distinct().count()
    else:
        scoped_prefs = Preference.objects.filter(application=user_app) if user_app else Preference.objects.none()
        total_applicants = 1 if user_app else 0
        with_roommate_req = 1 if (user_mutual_status and user_mutual_status.get("status") != "NONE") else 0

    stats = {
        "total_preferences": scoped_prefs.count(),
        "total_applicants": total_applicants,
        "with_roommate_req": with_roommate_req,
        "single_room_pct": round(scoped_prefs.filter(preferred_room_type="SINGLE").count() / max(1, scoped_prefs.count()) * 100, 1) if scoped_prefs.exists() else 0,
        "confirmed_pairs_count": len(confirmed_pairs),
    }

    context = {
        "preferences": preferences,
        "user_app": user_app,
        "user_prefs_by_rank": user_prefs_by_rank,
        "user_mutual_status": user_mutual_status,
        "available_hostels": available_hostels,
        "all_hostels": all_hostels,
        "stats": stats,
        "confirmed_pairs": confirmed_pairs,
        "demand_analytics": demand_analytics,
        "is_admin": is_admin,
        "is_warden": is_warden,
        "is_student": is_student,
        "warden_hostel": warden_hostel,
        "query": query,
        "hostel_filter": hostel_filter,
        "room_filter": room_filter,
        "rank_filter": rank_filter,
    }
    return render(request, "preferences/list.html", context)


@login_required
def roommate_requests_hub_view(request):
    """
    Dedicated In-App Roommate Requests & Synergy Review Hub:
    - Incoming Requests: inspect requester's academic profile, M5 lifestyle synergy breakdown (DPDP-compliant), and residency track record.
    - Accept Action: marks request ACCEPTED, auto-links reciprocal preferred_roommate_id, confirms mutual pair, and dispatches in-app notification.
    - Decline Action: marks request DECLINED, cleanly transitions requester to Individual Allocation Pool with M5 solver fallback, dispatches notification.
    - Outgoing Requests: displays outgoing status (Pending/Confirmed/Declined) with cancel option.
    - Request History Ledger: transparent audit trail of all past roommate requests.
    - Admin/Warden Overview: aggregated view across jurisdiction.
    """
    warden_assignment = None
    if request.user.is_authenticated:
        warden_assignment = WardenHostelAssignment.objects.filter(
            Q(user=request.user) | Q(warden_email__iexact=request.user.email)
        ).select_related("hostel").first()

    is_warden = bool(warden_assignment or (request.user.is_authenticated and ("warden" in request.user.username.lower() or "warden" in (request.user.email or "").lower())))
    is_admin = bool(request.user.is_authenticated and (request.user.is_superuser or (request.user.is_staff and not is_warden)))
    is_student = bool(request.user.is_authenticated and not is_admin and not is_warden)

    warden_hostel = warden_assignment.hostel if warden_assignment else None
    if is_warden and not warden_hostel:
        warden_hostel = Hostel.objects.filter(is_active=True).first()

    # Find student's active application
    user_app = getattr(request.user, "student_application", None)
    if not user_app:
        user_app = Application.objects.filter(
            Q(user=request.user) |
            Q(student_id=request.user.username) |
            Q(student_email__iexact=request.user.email)
        ).first()

    # Handle POST Actions (Accept, Decline, Cancel)
    if request.method == "POST":
        action = request.POST.get("action")
        req_id = request.POST.get("request_id")

        if not req_id:
            messages.error(request, "Invalid request ID provided.")
            return redirect("preferences:requests")

        req_obj = get_object_or_404(RoommateRequest, id=req_id)

        if action == "accept":
            # Target student confirms roommate
            if req_obj.target != user_app and not is_admin:
                messages.error(request, "You are not authorized to accept this roommate request.")
                return redirect("preferences:requests")

            req_obj.status = "ACCEPTED"
            req_obj.responded_at = timezone.now()
            req_obj.save()

            # Synchronize bi-directional preferences
            if user_app:
                pref1 = Preference.objects.filter(application=user_app, rank=1).first()
                if pref1:
                    pref1.preferred_roommate_id = req_obj.requester.student_id
                    pref1.save()
                else:
                    req_pref = req_obj.requester.preferences.filter(rank=1).first()
                    target_hostel = req_pref.preferred_hostel if req_pref else Hostel.objects.filter(is_active=True, gender_type=user_app.gender).first()
                    Preference.objects.create(
                        application=user_app,
                        rank=1,
                        preferred_hostel=target_hostel,
                        preferred_room_type="DOUBLE",
                        preferred_roommate_id=req_obj.requester.student_id,
                        institution_id=user_app.institution_id or "inst_default"
                    )

            # Ensure requester's preference has target
            Preference.objects.filter(application=req_obj.requester, rank=1).update(
                preferred_roommate_id=req_obj.target.student_id
            )

            # Mark any reverse pending request as accepted too
            RoommateRequest.objects.filter(requester=req_obj.target, target=req_obj.requester).update(
                status="ACCEPTED",
                responded_at=timezone.now()
            )

            # Notify Requester
            if req_obj.requester.user:
                NotificationService.send_in_app(
                    recipient_user=req_obj.requester.user,
                    subject=f"Roommate Request Confirmed: {user_app.student_name if user_app else 'Partner'}",
                    body=f"Great news! {user_app.student_name if user_app else 'Your requested roommate'} has accepted your roommate request. Your bi-directional mutual pair is now verified and locked for allocation.",
                    notification_type="ROOMMATE_ACCEPTED",
                    action_url="/preferences/requests/",
                    action_label="View Confirmed Pair",
                    institution_id=req_obj.institution_id
                )

            messages.success(
                request,
                f"Successfully confirmed mutual roommate pair with {req_obj.requester.student_name} ({req_obj.requester.student_id})! Both applications are now locked together."
            )
            return redirect("preferences:requests")

        elif action == "decline":
            # Target student declines request
            if req_obj.target != user_app and not is_admin:
                messages.error(request, "You are not authorized to decline this roommate request.")
                return redirect("preferences:requests")

            decline_reason = request.POST.get("decline_reason", "").strip() or "Candidate preferred individual allocation / alternative arrangement."
            req_obj.status = "DECLINED"
            req_obj.responded_at = timezone.now()
            req_obj.decline_reason = decline_reason
            req_obj.save()

            # Clean fallback for Requester: reset preferred_roommate_id to None
            Preference.objects.filter(
                application=req_obj.requester,
                preferred_roommate_id__iexact=req_obj.target.student_id
            ).update(preferred_roommate_id=None)

            # If reverse request exists, update it too
            RoommateRequest.objects.filter(requester=req_obj.target, target=req_obj.requester).update(
                status="DECLINED",
                responded_at=timezone.now(),
                decline_reason=decline_reason
            )

            # Notify Requester with graceful fallback explanation
            if req_obj.requester.user:
                NotificationService.send_in_app(
                    recipient_user=req_obj.requester.user,
                    subject=f"Roommate Request Update from {user_app.student_name if user_app else 'Candidate'}",
                    body=f"{user_app.student_name if user_app else 'The candidate'} was unable to confirm your roommate request. Your application has been smoothly transitioned to the Individual Allocation Pool. The M6 optimization solver will automatically assign your optimal roommate based on your M5 lifestyle compatibility score.",
                    notification_type="ROOMMATE_DECLINED",
                    action_url="/preferences/",
                    action_label="View Preferences",
                    institution_id=req_obj.institution_id
                )

            messages.info(
                request,
                f"Roommate request from {req_obj.requester.student_name} declined. Candidate has been smoothly transitioned to the Individual Allocation Pool."
            )
            return redirect("preferences:requests")

        elif action == "cancel":
            # Requester cancels their pending request
            if req_obj.requester != user_app and not is_admin:
                messages.error(request, "You are not authorized to cancel this request.")
                return redirect("preferences:requests")

            req_obj.status = "CANCELLED"
            req_obj.responded_at = timezone.now()
            req_obj.decline_reason = "Cancelled by requester."
            req_obj.save()

            Preference.objects.filter(
                application=req_obj.requester,
                preferred_roommate_id__iexact=req_obj.target.student_id
            ).update(preferred_roommate_id=None)

            messages.info(request, "Your roommate request has been cancelled.")
            return redirect("preferences:requests")

    # GET: Prepare Hub Data
    incoming_requests = []
    outgoing_requests = []
    history_requests = []
    confirmed_partner_info = None

    if user_app:
        # 1. Incoming Pending Requests
        incoming_qs = RoommateRequest.objects.filter(
            target=user_app,
            status="PENDING"
        ).select_related("requester", "requester__cycle")

        user_rank1 = user_app.preferences.filter(rank=1).select_related("preferred_hostel").first()

        for req in incoming_qs:
            breakdown = CompatibilityService.get_detailed_breakdown(user_app, req.requester)
            requester_rank1 = req.requester.preferences.filter(rank=1).select_related("preferred_hostel").first()
            hostel_match = bool(requester_rank1 and user_rank1 and requester_rank1.preferred_hostel_id == user_rank1.preferred_hostel_id)
            past_assignment = AllocationAssignment.objects.filter(
                application__student_id=req.requester.student_id
            ).select_related("bed__room__block__hostel", "draft").first()

            req.computed = {
                "breakdown": breakdown,
                "requester_rank1": requester_rank1,
                "user_rank1": user_rank1,
                "hostel_match": hostel_match,
                "past_assignment": past_assignment,
            }
            incoming_requests.append(req)

        # 2. Outgoing Requests
        outgoing_qs = RoommateRequest.objects.filter(
            requester=user_app
        ).select_related("target", "target__cycle").order_by("-created_at")

        for req in outgoing_qs:
            breakdown = CompatibilityService.get_detailed_breakdown(user_app, req.target)
            target_rank1 = req.target.preferences.filter(rank=1).select_related("preferred_hostel").first()
            req.computed = {
                "breakdown": breakdown,
                "target_rank1": target_rank1,
            }
            outgoing_requests.append(req)

        # 3. Request History Ledger (Resolved requests)
        history_requests = list(
            RoommateRequest.objects.filter(
                Q(requester=user_app) | Q(target=user_app)
            ).exclude(status="PENDING")
            .select_related("requester", "target")
            .order_by("-updated_at")[:20]
        )

        # 4. Confirmed Mutual Partner Info (if verified)
        mutual_status = PreferenceService.check_roommate_mutual_status(user_app)
        if mutual_status.get("status") == "MUTUAL_CONFIRMED":
            partner_id = mutual_status.get("target_id")
            partner_app = Application.objects.filter(cycle=user_app.cycle, student_id=partner_id).first()
            if partner_app:
                breakdown = CompatibilityService.get_detailed_breakdown(user_app, partner_app)
                partner_rank1 = partner_app.preferences.filter(rank=1).select_related("preferred_hostel").first()
                past_assignment = AllocationAssignment.objects.filter(
                    application__student_id=partner_app.student_id
                ).select_related("bed__room__block__hostel", "draft").first()
                confirmed_partner_info = {
                    "partner_app": partner_app,
                    "breakdown": breakdown,
                    "partner_rank1": partner_rank1,
                    "past_assignment": past_assignment,
                }

    # Admin / Warden Campus-Wide Overview
    admin_requests = []
    admin_stats = {}
    if is_admin or is_warden:
        admin_qs = RoommateRequest.objects.select_related("requester", "target", "requester__cycle")
        if is_warden and warden_hostel:
            admin_qs = admin_qs.filter(
                Q(requester__preferences__preferred_hostel=warden_hostel) |
                Q(target__preferences__preferred_hostel=warden_hostel)
            ).distinct()

        status_filter = request.GET.get("filter_status", "").strip()
        if status_filter:
            admin_qs = admin_qs.filter(status=status_filter)

        search_q = request.GET.get("q", "").strip()
        if search_q:
            admin_qs = admin_qs.filter(
                Q(requester__student_name__icontains=search_q) |
                Q(requester__student_id__icontains=search_q) |
                Q(target__student_name__icontains=search_q) |
                Q(target__student_id__icontains=search_q)
            )

        admin_stats = {
            "total": admin_qs.count(),
            "pending": admin_qs.filter(status="PENDING").count(),
            "accepted": admin_qs.filter(status="ACCEPTED").count(),
            "declined": admin_qs.filter(status="DECLINED").count(),
        }
        admin_requests = list(admin_qs[:50])
        for r in admin_requests:
            r.compat_score = round(CompatibilityService.calculate_pairwise_score(r.requester, r.target) * 100)

    context = {
        "user_app": user_app,
        "incoming_requests": incoming_requests,
        "outgoing_requests": outgoing_requests,
        "history_requests": history_requests,
        "confirmed_partner_info": confirmed_partner_info,
        "admin_requests": admin_requests,
        "admin_stats": admin_stats,
        "is_admin": is_admin,
        "is_warden": is_warden,
        "is_student": is_student,
        "warden_hostel": warden_hostel,
    }
    return render(request, "preferences/requests.html", context)

