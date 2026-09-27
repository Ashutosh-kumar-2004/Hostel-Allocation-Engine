from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from apps.core.decorators import warden_or_admin_required
from .models import AllocationDraft, AllocationAssignment
from .services import AllocationService, SimulationExecutionService
from apps.applications.models import AllocationCycle, Application
from apps.inventory.models import Hostel, Bed, WardenHostelAssignment

@login_required
@warden_or_admin_required
def trigger_allocation_view(request):
    """
    POST endpoint to trigger a constraint-respecting allocation run.
    Produces an isolated draft for warden review with atomic mutual pairing.
    """
    if request.method != "POST":
        return redirect("allocation:draft_list")

    cycle_id = request.POST.get("cycle_id")
    seed_str = request.POST.get("random_seed", "42")
    try:
        random_seed = int(seed_str)
    except ValueError:
        random_seed = 42

    cycle = (
        get_object_or_404(AllocationCycle, id=cycle_id)
        if cycle_id
        else AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING"]).first() or AllocationCycle.objects.first()
    )
    if not cycle:
        messages.error(request, "No active allocation cycle found.")
        return redirect("allocation:draft_list")

    # Determine hostel scope
    warden_assign = getattr(request, "warden_assignment", None)
    if not warden_assign:
        warden_assign = WardenHostelAssignment.objects.filter(user=request.user).first()

    scoped_hostel_id = None
    if warden_assign and not (request.user.is_superuser or request.user.is_staff):
        scoped_hostel_id = str(warden_assign.hostel_id)
    else:
        req_hostel = request.POST.get("hostel_id", "").strip()
        if req_hostel and req_hostel != "ALL":
            scoped_hostel_id = req_hostel

    try:
        actor_email = request.user.email or f"{request.user.username}@university.edu"
        draft = AllocationService.run_allocation(
            cycle_id=str(cycle.id),
            random_seed=random_seed,
            actor_email=actor_email,
            hostel_id=scoped_hostel_id
        )
        messages.success(
            request,
            f"Draft {draft.run_identifier} generated successfully! {draft.assigned_count} beds allocated out of {draft.total_applicants} applicants. Awaiting Warden Review."
        )
        return redirect("allocation:draft_detail", draft_id=draft.id)
    except Exception as e:
        messages.error(request, f"Allocation run error: {str(e)}")
        return redirect("allocation:draft_list")

@login_required
@warden_or_admin_required
def draft_list_view(request):
    """
    Lists allocation drafts for the cycle with trigger console and metrics.
    """
    drafts = AllocationDraft.objects.select_related("cycle").all().order_by("-created_at")
    cycles = AllocationCycle.objects.all().order_by("-application_start")
    active_cycle = AllocationCycle.objects.filter(status__in=["OPEN", "PROCESSING"]).first() or cycles.first()

    available_hostels = Hostel.objects.filter(is_active=True).order_by("name")
    warden_assign = getattr(request, "warden_assignment", None)
    if not warden_assign:
        warden_assign = WardenHostelAssignment.objects.filter(user=request.user).first()
    warden_hostel = warden_assign.hostel if warden_assign else None

    # Stats for launch console
    total_eligible = Application.objects.filter(status__in=["SUBMITTED", "ELIGIBLE"]).count()
    total_available_beds = Bed.objects.filter(status="AVAILABLE").count()

    context = {
        "drafts": drafts,
        "cycles": cycles,
        "active_cycle": active_cycle,
        "available_hostels": available_hostels,
        "warden_hostel": warden_hostel,
        "total_eligible": total_eligible,
        "total_available_beds": total_available_beds,
    }
    return render(request, "allocation/draft_list.html", context)

@login_required
@warden_or_admin_required
def draft_detail_view(request, draft_id):
    """
    Inspects a specific allocation draft and assignments.
    Filterable by hostel, room type, and search query.
    """
    draft = get_object_or_404(AllocationDraft.objects.select_related("cycle"), id=draft_id)
    qs = AllocationAssignment.objects.filter(draft=draft).select_related(
        "application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"
    )

    query = request.GET.get("q", "").strip()
    hostel_filter = request.GET.get("hostel", "").strip()
    room_type_filter = request.GET.get("room_type", "").strip()

    if query:
        qs = qs.filter(
            Q(application__student_name__icontains=query) |
            Q(application__student_id__icontains=query) |
            Q(bed__room__room_number__icontains=query)
        )

    if hostel_filter:
        qs = qs.filter(bed__room__block__hostel_id=hostel_filter)

    if room_type_filter:
        qs = qs.filter(bed__room__room_type=room_type_filter)

    assignments = list(qs.order_by("bed__room__block__hostel__name", "bed__room__room_number", "bed__bed_identifier"))

    # Draft summary metrics
    metrics = draft.summary_metrics or {}
    available_hostels = Hostel.objects.filter(is_active=True).order_by("name")

    context = {
        "draft": draft,
        "assignments": assignments,
        "metrics": metrics,
        "available_hostels": available_hostels,
        "query": query,
        "hostel_filter": hostel_filter,
        "room_type_filter": room_type_filter,
    }
    return render(request, "allocation/draft_detail.html", context)

def student_explanation_view(request, assignment_id):
    """
    9E: Explainable Allocation Result View.
    Allows an authenticated student to view "Why was I assigned this room?" with a transparent breakdown
    of preferences, cooling matches, accessibility, mutual roommates, and compatibility scores.
    """
    if not request.user.is_authenticated:
        messages.error(request, "Please log in to view allocation explanations.")
        return redirect("login")

    assignment = get_object_or_404(
        AllocationAssignment.objects.select_related(
            "draft", "draft__cycle", "application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"
        ),
        id=assignment_id
    )
    return render(request, "allocation/explanation.html", {"assignment": assignment})

@login_required
@warden_or_admin_required
def what_if_simulation_view(request):
    """
    9E: Warden What-if Allocation Simulation Console.
    1. Guarded by authoritative @login_required and @warden_or_admin_required.
    2. Enforces structural single-hostel scoping: Wardens are LOCKED to their assigned hostel.
       Only superusers/staff can switch hostels via query parameters.
    3. Runs on REAL student applications, preferences, and compatibility responses from DB.
    4. Business queries, baseline stats, input validations, and execution delegated to SimulationExecutionService.
    """
    hostels = Hostel.objects.filter(is_active=True)
    warden_assign = getattr(request, "warden_assignment", None)

    # Enforce structural hostel scoping:
    # A non-admin Warden is strictly scoped to their assigned hostel and CANNOT bypass via GET/POST parameter
    if warden_assign and not (request.user.is_superuser or request.user.is_staff):
        current_hostel = warden_assign.hostel
    else:
        hostel_id = request.GET.get("hostel_id") or request.POST.get("hostel_id")
        if hostel_id:
            current_hostel = get_object_or_404(Hostel, id=hostel_id)
        else:
            current_hostel = hostels.filter(code="BH-4").first() or hostels.first()

    # Delegate inventory and baseline calculation to service
    hostel_ctx = SimulationExecutionService.get_hostel_context(current_hostel)
    active_cycle = hostel_ctx["active_cycle"]
    sim_beds = hostel_ctx["sim_beds"]

    # Load REAL student applicants from database for this cycle and hostel
    sim_applicants = SimulationExecutionService.load_real_applicants(current_hostel, active_cycle)

    result = None
    pref_weight = 65
    comp_weight = 35
    reserved_quota = 15
    hypo_block = ""
    hypo_cooling = "No change"
    excluded_blocks = []
    seed_val = 88213

    if request.method == "POST":
        action = request.POST.get("action", "run_simulation")
        
        # If Warden/Admin requests to save this scenario snapshot
        if action == "save_scenario":
            scenario_name = request.POST.get("scenario_name", "Scenario Snapshot").strip()
            seed_val = int(request.POST.get("seed", 88213) or 88213)
            pref_weight = int(request.POST.get("pref_weight", 65) or 65)
            comp_weight = 100 - pref_weight
            reserved_quota = int(request.POST.get("reserved_quota", 15) or 15)
            hypo_block = request.POST.get("hypo_block", "")
            hypo_cooling = request.POST.get("hypo_cooling", "No change")
            excluded_blocks = request.POST.getlist("excluded_blocks")

            # Run deterministic simulation for snapshot saving
            sim_data = SimulationExecutionService.validate_and_execute_simulation(
                post_data=request.POST,
                sim_beds=sim_beds,
                sim_applicants=sim_applicants
            )
            result = sim_data["result"]

            # Save in strict isolation - NEVER updates Bed or Application models
            from .models import SavedSimulationScenario
            scenario = SavedSimulationScenario.objects.create(
                hostel=current_hostel,
                cycle=active_cycle,
                created_by=request.user if request.user.is_authenticated else None,
                name=scenario_name or f"Scenario (Seed {seed_val})",
                seed=seed_val,
                pref_weight=pref_weight,
                comp_weight=comp_weight,
                reserved_quota=reserved_quota,
                hypo_block=hypo_block,
                hypo_cooling=hypo_cooling,
                excluded_blocks=excluded_blocks,
                result_metrics={
                    "sim_allocated": result.sim_allocated,
                    "sim_waitlisted": result.sim_waitlisted,
                    "sim_first_pref_met_pct": result.sim_first_pref_met_pct,
                    "sim_avg_compatibility": result.sim_avg_compatibility,
                    "delta_allocated": result.delta_allocated,
                    "delta_waitlisted": result.delta_waitlisted,
                    "delta_pref_pts": result.delta_pref_pts,
                    "delta_compatibility": result.delta_compatibility,
                    "summary": result.summary
                },
                simulated_allocations=result.bed_allocations,
                institution_id=current_hostel.institution_id
            )
            messages.success(request, f"Scenario '{scenario.name}' saved successfully! (Simulation outcome recorded without modifying live beds or applications).")
            
        else:
            sim_data = SimulationExecutionService.validate_and_execute_simulation(
                post_data=request.POST,
                sim_beds=sim_beds,
                sim_applicants=sim_applicants
            )
            result = sim_data["result"]
            pref_weight = sim_data["pref_weight"]
            comp_weight = sim_data["comp_weight"]
            reserved_quota = sim_data["reserved_quota"]
            hypo_block = sim_data["hypo_block"]
            hypo_cooling = sim_data["hypo_cooling"]
            excluded_blocks = sim_data["excluded_blocks"]
            seed_val = sim_data["seed_val"]
            messages.success(request, f"Simulation executed successfully (Seed {seed_val})! Evaluated {sim_data['applicant_count']} real student applicants. Live inventory remains unmodified.")

    # Check if user requested to view a specific saved scenario
    scenario_id = request.GET.get("scenario_id")
    loaded_scenario = None
    if scenario_id:
        from .models import SavedSimulationScenario
        loaded_scenario = SavedSimulationScenario.objects.filter(id=scenario_id, hostel=current_hostel).first()
        if loaded_scenario:
            pref_weight = loaded_scenario.pref_weight
            comp_weight = loaded_scenario.comp_weight
            reserved_quota = loaded_scenario.reserved_quota
            hypo_block = loaded_scenario.hypo_block
            hypo_cooling = loaded_scenario.hypo_cooling
            excluded_blocks = loaded_scenario.excluded_blocks
            seed_val = loaded_scenario.seed
            # Reconstruct simulation result for viewing
            sim_data = SimulationExecutionService.validate_and_execute_simulation(
                post_data={
                    "pref_weight": pref_weight,
                    "comp_weight": comp_weight,
                    "reserved_quota": reserved_quota,
                    "hypo_block": hypo_block,
                    "hypo_cooling": hypo_cooling,
                    "excluded_blocks": excluded_blocks,
                    "seed": seed_val,
                },
                sim_beds=sim_beds,
                sim_applicants=sim_applicants
            )
            result = sim_data["result"]
            messages.info(request, f"Loaded saved scenario '{loaded_scenario.name}' (Seed {seed_val}).")

    # Fetch recently saved simulation scenarios for this hostel
    from .models import SavedSimulationScenario
    saved_scenarios = SavedSimulationScenario.objects.filter(hostel=current_hostel).order_by("-created_at")[:20]

    context = {
        "current_hostel": current_hostel,
        "saved_scenarios": saved_scenarios,
        "loaded_scenario": loaded_scenario,
        "hostels": hostels,
        "active_cycle": active_cycle,
        "blocks": hostel_ctx["blocks"],
        "baseline_stats": hostel_ctx["baseline_stats"],
        "baseline_block_occupancies": hostel_ctx["baseline_block_occupancies"],
        "real_applicant_count": len(sim_applicants),
        "result": result,
        "pref_weight": pref_weight,
        "comp_weight": comp_weight,
        "reserved_quota": reserved_quota,
        "hypo_block": hypo_block,
        "hypo_cooling": hypo_cooling,
        "excluded_blocks": excluded_blocks,
        "seed_val": seed_val,
    }
    return render(request, "allocation/simulation.html", context)


