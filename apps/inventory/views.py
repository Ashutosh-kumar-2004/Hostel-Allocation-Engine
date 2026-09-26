from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.decorators import warden_or_admin_required
from django.db.models import Prefetch, Count, Q
from django.utils import timezone
from .models import Hostel, Block, Floor, Room, Bed, WardenHostelAssignment, RoomChangeRequest
from apps.audit.models import AuditEntry

from .services import InventoryService

def get_user_inventory_scope(request):
    """
    Returns (is_admin, is_warden, warden_hostel, scope)
    - If admin: scope is None (can manage ANY hostel)
    - If warden: scope is warden_hostel (can ONLY manage their assigned hostel)
    """
    user = request.user
    warden_assign = getattr(request, "warden_assignment", None)
    if not warden_assign and user.is_authenticated:
        warden_assign = WardenHostelAssignment.objects.filter(user=user).select_related("hostel").first()
        if not warden_assign and user.email:
            warden_assign = WardenHostelAssignment.objects.filter(warden_email__iexact=user.email).select_related("hostel").first()

    is_warden = bool(warden_assign or (user.is_authenticated and "warden" in user.username.lower()))
    is_admin = bool(user.is_authenticated and (user.is_superuser or (user.is_staff and not is_warden)))
    warden_hostel = warden_assign.hostel if warden_assign else None
    
    scope = None if is_admin else warden_hostel
    return is_admin, is_warden, warden_hostel, scope

def hostel_list_view(request):
    """
    Overview of all hostels and their operational summaries.
    """
    is_admin, is_warden, warden_hostel, scope = get_user_inventory_scope(request)
    hostels = Hostel.objects.filter(is_active=True).prefetch_related(
        "blocks__floors",
        "warden_assignment"
    ).annotate(
        total_rooms=Count("blocks__rooms", distinct=True),
        total_beds=Count("blocks__rooms__beds", distinct=True),
        occupied_beds=Count("blocks__rooms__beds", filter=Q(blocks__rooms__beds__status__in=["OCCUPIED", "RESERVED"]), distinct=True),
        available_beds=Count("blocks__rooms__beds", filter=Q(blocks__rooms__beds__status="AVAILABLE"), distinct=True),
    )
    return render(request, "inventory/hostel_list.html", {
        "hostels": hostels,
        "is_admin": is_admin,
        "is_warden": is_warden,
        "warden_hostel": warden_hostel,
    })


def student_explorer_view(request):
    """
    9C: Interactive Residential Booking & Hostel Explorer.
    Hierarchical selection: Room Type -> Seater Category -> Hostel -> Room -> Bed/Seat
    with live Residential Cart and submission workflow.
    """
    import json
    from apps.applications.models import Application, AllocationCycle
    from apps.preferences.models import Preference

    student_gender = None
    student_app = None
    if request.user.is_authenticated:
        student_app = getattr(request.user, "student_application", None)
        if not student_app:
            student_app = Application.objects.filter(student_id=request.user.username).first()
            if not student_app and request.user.email:
                student_app = Application.objects.filter(student_email__iexact=request.user.email).first()
        if student_app:
            student_gender = student_app.gender

    # Exploratory View: Enables student to explore accommodation options present throughout the university
    selected_gender = request.GET.get("gender", "")
    if not selected_gender and student_gender:
        selected_gender = student_gender

    hostels_qs = Hostel.objects.filter(is_active=True).prefetch_related(
        Prefetch("blocks", queryset=Block.objects.order_by("code")),
        Prefetch("blocks__floors", queryset=Floor.objects.order_by("floor_number")),
        Prefetch("blocks__rooms", queryset=Room.objects.filter(is_active=True).select_related("floor").prefetch_related("beds").order_by("room_number")),
    )
    if selected_gender:
        hostels_qs = hostels_qs.filter(Q(gender_type=selected_gender) | Q(gender_type="C"))

    # Build hierarchical tree for exploratory interactive breakdown and bed-map representation
    # Structure: Hostel -> Blocks -> Floors -> Rooms -> Beds, complete with stats
    tree_data = []
    for h in hostels_qs:
        total_beds = 0
        available_beds = 0
        occupied_beds = 0
        reserved_beds = 0
        maintenance_beds = 0

        h_rooms = []
        blocks_data = []

        for b in h.blocks.all():
            b_floors_map = {}
            # Initialize floors from defined floor models
            for fl in b.floors.all():
                b_floors_map[fl.floor_number] = {
                    "id": str(fl.id),
                    "floor_number": fl.floor_number,
                    "name": fl.name or f"Floor {fl.floor_number}",
                    "rooms": []
                }

            b_rooms = []
            for r in b.rooms.all():
                r_beds = [
                    {
                        "id": str(bed.id),
                        "identifier": bed.bed_identifier,
                        "status": bed.status,
                        "status_display": bed.get_status_display(),
                        "occupant": bed.occupant_name or "",
                        "label": f"{r.room_number}-Bed {bed.bed_identifier}"
                    }
                    for bed in r.beds.all()
                ]

                # Tally bed stats
                for bed_dict in r_beds:
                    total_beds += 1
                    st = bed_dict["status"]
                    if st == "AVAILABLE":
                        available_beds += 1
                    elif st == "OCCUPIED":
                        occupied_beds += 1
                    elif st == "RESERVED":
                        reserved_beds += 1
                    elif st == "MAINTENANCE":
                        maintenance_beds += 1

                room_dict = {
                    "id": str(r.id),
                    "room_number": r.room_number,
                    "block_id": str(b.id),
                    "block_name": b.name,
                    "block_code": b.code,
                    "floor_number": r.floor_number,
                    "cooling_type": r.cooling_type,
                    "cooling_display": r.get_cooling_type_display(),
                    "room_type": r.room_type,
                    "room_type_display": r.get_room_type_display(),
                    "capacity": r.bed_capacity,
                    "attached_washroom": r.has_attached_washroom,
                    "facilities": r.facilities,
                    "beds": r_beds,
                }
                h_rooms.append(room_dict)
                b_rooms.append(room_dict)

                fl_num = r.floor_number
                if fl_num not in b_floors_map:
                    b_floors_map[fl_num] = {
                        "id": f"fl-{b.id}-{fl_num}",
                        "floor_number": fl_num,
                        "name": f"Floor {fl_num}",
                        "rooms": []
                    }
                b_floors_map[fl_num]["rooms"].append(room_dict)

            # Sort floors by floor_number
            sorted_floors = sorted(b_floors_map.values(), key=lambda x: x["floor_number"])

            blocks_data.append({
                "id": str(b.id),
                "code": b.code,
                "name": b.name,
                "number_of_floors": b.number_of_floors,
                "rooms": b_rooms,
                "floors": sorted_floors
            })

        tree_data.append({
            "id": str(h.id),
            "code": h.code,
            "name": h.name,
            "gender": h.gender_type,
            "gender_display": h.get_gender_type_display(),
            "description": h.description,
            "total_beds": total_beds,
            "available_beds": available_beds,
            "occupied_beds": occupied_beds,
            "reserved_beds": reserved_beds,
            "maintenance_beds": maintenance_beds,
            "vacant_beds": available_beds,
            "rooms": h_rooms,
            "blocks": blocks_data,
        })

    active_cycle = AllocationCycle.objects.order_by("-created_at").first()

    context = {
        "tree_data_json": json.dumps(tree_data),
        "hostels": hostels_qs,
        "student_app": student_app,
        "student_gender": student_gender,
        "active_cycle": active_cycle,
    }
    return render(request, "inventory/explorer.html", context)



@login_required
@warden_or_admin_required
def warden_bed_map_view(request, hostel_id=None):
    """
    9D & 9A: Interactive Warden Bed Map.
    Scoped to the assigned hostel for Wardens; accessible across all hostels for Admins.
    Allows adding floors, rooms, and beds, and deleting vacant rooms and beds.
    """
    is_admin, is_warden, warden_hostel, scope = get_user_inventory_scope(request)
    hostels = Hostel.objects.filter(is_active=True).order_by("code")

    if is_warden and not request.user.is_superuser:
        current_hostel = warden_hostel or hostels.first()
    elif hostel_id:
        current_hostel = get_object_or_404(Hostel, id=hostel_id)
    else:
        current_hostel = hostels.filter(code="BH-4").first() or hostels.first()

    blocks = Block.objects.filter(hostel=current_hostel).prefetch_related(
        Prefetch("floors", queryset=Floor.objects.order_by("floor_number")),
        Prefetch(
            "rooms",
            queryset=Room.objects.select_related("floor").prefetch_related("beds").order_by("room_number")
        )
    )

    for block in blocks:
        for room in block.rooms.all():
            room.has_active_allocations = any(b.status in ["OCCUPIED", "RESERVED"] for b in room.beds.all())

    # Floor wise aggregation
    floor_data = []
    all_rooms = Room.objects.filter(block__hostel=current_hostel).prefetch_related("beds")
    floors = Floor.objects.filter(block__hostel=current_hostel).order_by("floor_number")

    for fl in floors:
        fl_rooms = [r for r in all_rooms if r.floor_id == fl.id or (not r.floor_id and r.floor_number == fl.floor_number)]
        floor_data.append({
            "floor": fl,
            "rooms": fl_rooms
        })

    # Stats for current hostel
    beds_qs = Bed.objects.filter(room__block__hostel=current_hostel)
    stats = {
        "total_beds": beds_qs.count(),
        "available": beds_qs.filter(status="AVAILABLE").count(),
        "occupied": beds_qs.filter(status="OCCUPIED").count(),
        "reserved": beds_qs.filter(status="RESERVED").count(),
        "maintenance": beds_qs.filter(status="MAINTENANCE").count(),
    }

    can_manage_current_hostel = bool(is_admin or (warden_hostel and current_hostel == warden_hostel))

    context = {
        "hostels": hostels,
        "current_hostel": current_hostel,
        "blocks": blocks,
        "floor_data": floor_data,
        "stats": stats,
        "is_admin": is_admin,
        "is_warden": is_warden,
        "warden_hostel": warden_hostel,
        "can_manage_current_hostel": can_manage_current_hostel,
    }
    return render(request, "inventory/bed_map.html", context)


@login_required
def admin_warden_assignments_view(request):
    """
    9A & Figure 3: System Administrator Warden Assignment Control.
    System Administrator provisions Wardens (with user accounts and passwords)
    and assigns them 1-to-1 to hostels.
    """
    is_admin, _, _, _ = get_user_inventory_scope(request)
    if not is_admin:
        messages.error(request, "Permission Denied: Only System Administrators can configure Warden assignments.")
        return redirect("dashboard")

    if request.method == "POST":
        hostel_id = request.POST.get("hostel_id")
        warden_name = request.POST.get("warden_name", "").strip()
        warden_email = request.POST.get("warden_email", "").strip()
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "warden123").strip()
        notes = request.POST.get("notes", "").strip()

        try:
            assignment = InventoryService.create_and_assign_warden(
                hostel_id=hostel_id,
                warden_name=warden_name,
                warden_email=warden_email,
                username=username,
                password=password,
                notes=notes,
                actor_email=request.user.email or f"{request.user.username}@university.edu",
                actor_id=str(request.user.id)
            )
            messages.success(request, f"Warden {assignment.warden_name} ({assignment.warden_email}) successfully assigned to {assignment.hostel.name}.")
        except Exception as e:
            messages.error(request, f"Failed to assign warden: {str(e)}")

        return redirect("inventory:warden_assignments")

    hostels = Hostel.objects.filter(is_active=True).select_related("warden_assignment").order_by("code")
    assignments = WardenHostelAssignment.objects.select_related("hostel", "user").all().order_by("hostel__code")
    return render(request, "inventory/warden_assignments.html", {"hostels": hostels, "assignments": assignments})


@login_required
def create_hostel_view(request):
    """
    POST endpoint: System Administrator creates a new Hostel.
    Automatically creates Block A and Ground Floor so rooms can be immediately provisioned.
    """
    is_admin, _, _, _ = get_user_inventory_scope(request)
    if not is_admin:
        messages.error(request, "Permission Denied: Only System Administrators can create new hostels.")
        return redirect("inventory:list")

    if request.method == "POST":
        code = request.POST.get("code", "")
        name = request.POST.get("name", "")
        gender_type = request.POST.get("gender_type", "M")
        description = request.POST.get("description", "")
        address = request.POST.get("address", "")

        try:
            hostel = InventoryService.create_hostel(
                code=code,
                name=name,
                gender_type=gender_type,
                description=description,
                address=address,
                actor_email=request.user.email or f"{request.user.username}@university.edu",
                actor_id=str(request.user.id)
            )
            messages.success(request, f"Hostel {hostel.name} ({hostel.code}) successfully created with Block A and Ground Floor.")
            return redirect("inventory:bed_map_hostel", hostel_id=hostel.id)
        except Exception as e:
            messages.error(request, f"Failed to create hostel: {str(e)}")

    return redirect("inventory:list")


@login_required
@warden_or_admin_required
def create_floor_view(request):
    """
    POST endpoint: Add a new Floor to a Block.
    Allowed for Admin across all hostels; for Warden strictly within their assigned hostel.
    """
    if request.method == "POST":
        block_id = request.POST.get("block_id")
        floor_num = int(request.POST.get("floor_number", 0))
        name = request.POST.get("name", "").strip()
        is_admin, is_warden, warden_hostel, scope = get_user_inventory_scope(request)

        try:
            floor = InventoryService.create_floor(
                block_id=block_id,
                floor_number=floor_num,
                name=name,
                actor_email=request.user.email or f"{request.user.username}@university.edu",
                actor_id=str(request.user.id),
                user_hostel_scope=scope
            )
            messages.success(request, f"Floor '{floor.name}' added to {floor.block.name}.")
            return redirect("inventory:bed_map_hostel", hostel_id=floor.block.hostel.id)
        except Exception as e:
            messages.error(request, f"Failed to add floor: {str(e)}")

    return redirect("inventory:bed_map")


@login_required
@warden_or_admin_required
def create_room_view(request):
    """
    POST endpoint: Add a Room with initial beds.
    Allowed for Admin across all hostels; for Warden strictly within their assigned hostel.
    """
    if request.method == "POST":
        block_id = request.POST.get("block_id")
        room_number = request.POST.get("room_number", "").strip()
        floor_number = int(request.POST.get("floor_number", 0))
        room_type = request.POST.get("room_type", "DOUBLE")
        cooling_type = request.POST.get("cooling_type", "COOLER")
        capacity = int(request.POST.get("capacity", 2))
        is_accessible = request.POST.get("is_accessible") in ["true", "1", "on", True]

        is_admin, is_warden, warden_hostel, scope = get_user_inventory_scope(request)
        try:
            room = InventoryService.create_room(
                block_id=block_id,
                room_number=room_number,
                floor_number=floor_number,
                room_type=room_type,
                cooling_type=cooling_type,
                capacity=capacity,
                is_accessible=is_accessible,
                actor_email=request.user.email or f"{request.user.username}@university.edu",
                actor_id=str(request.user.id),
                user_hostel_scope=scope
            )
            messages.success(request, f"Room {room.room_number} ({room.get_room_type_display()}, {room.get_cooling_type_display()}) successfully added with {capacity} initial beds.")
            return redirect("inventory:bed_map_hostel", hostel_id=room.block.hostel.id)
        except Exception as e:
            messages.error(request, f"Failed to create room: {str(e)}")

    return redirect("inventory:bed_map")


@login_required
@warden_or_admin_required
def delete_room_view(request, room_id):
    """
    POST endpoint: Delete Room and associated beds.
    SAFEGUARD: Rejects deletion if any bed in the room is OCCUPIED or RESERVED.
    Allowed for Admin across all hostels; for Warden strictly within their assigned hostel.
    """
    if request.method == "POST":
        is_admin, is_warden, warden_hostel, scope = get_user_inventory_scope(request)
        room = get_object_or_404(Room, id=room_id)
        hostel_id = room.block.hostel.id

        try:
            InventoryService.delete_room(
                room_id=str(room.id),
                actor_email=request.user.email or f"{request.user.username}@university.edu",
                actor_id=str(request.user.id),
                user_hostel_scope=scope
            )
            messages.success(request, f"Room {room.room_number} and all its vacant beds were successfully deleted.")
        except Exception as e:
            messages.error(request, f"Cannot delete room: {str(e)}")

        return redirect("inventory:bed_map_hostel", hostel_id=hostel_id)
    return redirect("inventory:bed_map")


@login_required
@warden_or_admin_required
def create_bed_view(request):
    """
    POST endpoint: Add a new Bed to a Room.
    Allowed for Admin across all hostels; for Warden strictly within their assigned hostel.
    """
    if request.method == "POST":
        room_id = request.POST.get("room_id")
        bed_identifier = request.POST.get("bed_identifier", "").strip()
        is_admin, is_warden, warden_hostel, scope = get_user_inventory_scope(request)

        try:
            bed = InventoryService.create_bed(
                room_id=room_id,
                bed_identifier=bed_identifier,
                actor_email=request.user.email or f"{request.user.username}@university.edu",
                actor_id=str(request.user.id),
                user_hostel_scope=scope
            )
            messages.success(request, f"Bed {bed.bed_identifier} added to Room {bed.room.room_number}.")
            return redirect("inventory:bed_map_hostel", hostel_id=bed.room.block.hostel.id)
        except Exception as e:
            messages.error(request, f"Failed to add bed: {str(e)}")

    return redirect("inventory:bed_map")


@login_required
@warden_or_admin_required
def delete_bed_view(request, bed_id):
    """
    POST endpoint: Delete a Bed from a Room.
    SAFEGUARD: Rejects deletion if bed is OCCUPIED or RESERVED.
    Allowed for Admin across all hostels; for Warden strictly within their assigned hostel.
    """
    if request.method == "POST":
        is_admin, is_warden, warden_hostel, scope = get_user_inventory_scope(request)
        bed = get_object_or_404(Bed, id=bed_id)
        hostel_id = bed.room.block.hostel.id
        room_num = bed.room.room_number
        bed_ident = bed.bed_identifier

        try:
            InventoryService.delete_bed(
                bed_id=str(bed.id),
                actor_email=request.user.email or f"{request.user.username}@university.edu",
                actor_id=str(request.user.id),
                user_hostel_scope=scope
            )
            messages.success(request, f"Vacant Bed {bed_ident} deleted from Room {room_num}.")
        except Exception as e:
            messages.error(request, f"Cannot delete bed: {str(e)}")

        return redirect("inventory:bed_map_hostel", hostel_id=hostel_id)
    return redirect("inventory:bed_map")



from apps.applications.models import Application

def room_change_requests_view(request):
    """
    9E & Figure 5: Room Change Request Flow.
    Students submit change requests; Wardens review, approve or reject them.
    Scoped strictly to the Warden's assigned hostel and gender-compatible recommendations.
    """
    user = request.user
    
    # 1. Determine Warden Assignment & Scope
    warden_assignment = None
    if user.is_authenticated:
        warden_assignment = WardenHostelAssignment.objects.filter(user=user).select_related("hostel").first()
        if not warden_assignment and user.email:
            warden_assignment = WardenHostelAssignment.objects.filter(warden_email__iexact=user.email).select_related("hostel").first()

    is_admin = bool(user.is_authenticated and (user.is_superuser or (user.is_staff and not warden_assignment)))
    is_warden = bool(warden_assignment or (user.is_authenticated and "warden" in user.username.lower()))
    warden_hostel = warden_assignment.hostel if warden_assignment else None

    if request.method == "POST":
        action = request.POST.get("action")
        req_id = request.POST.get("request_id")
        
        if action == "create":
            # Form submission is only permitted for students
            student_id = request.POST.get("student_id")
            student_name = request.POST.get("student_name")
            student_email = request.POST.get("student_email")
            current_bed_id = request.POST.get("current_bed_id")
            cooling_pref = request.POST.get("preferred_cooling", "AC")
            room_pref = request.POST.get("preferred_room_type", "DOUBLE")
            reason = request.POST.get("reason", "")

            cur_bed = get_object_or_404(Bed, id=current_bed_id)
            RoomChangeRequest.objects.create(
                student_id=student_id,
                student_name=student_name,
                student_email=student_email,
                current_bed=cur_bed,
                preferred_cooling=cooling_pref,
                preferred_room_type=room_pref,
                reason=reason,
                status="PENDING"
            )
            messages.success(request, "Room Change Request submitted successfully! Your Warden will review it.")
            return redirect("inventory:room_changes")

        elif action in ["approve", "reject"]:
            req_obj = get_object_or_404(RoomChangeRequest, id=req_id)

            # Security check: If user is a warden with an assigned hostel, they cannot approve/reject requests outside their hostel
            if warden_hostel and not is_admin:
                req_hostel = req_obj.current_bed.room.block.hostel
                if req_hostel.id != warden_hostel.id:
                    messages.error(request, f"Permission denied: You can only review requests for your assigned hostel ({warden_hostel.name}).")
                    return redirect("inventory:room_changes")

            remarks = request.POST.get("remarks", "")
            
            if action == "approve":
                target_bed_id = request.POST.get("allocated_bed_id")
                target_bed = None
                if target_bed_id:
                    target_bed = get_object_or_404(Bed, id=target_bed_id)

                    # Range & Scope Check: Warden can only allocate beds within their assigned hostel range
                    if warden_hostel and not is_admin:
                        target_hostel = target_bed.room.block.hostel
                        if target_hostel.id != warden_hostel.id:
                            messages.error(request, f"Access Violation: Bed {target_bed} is outside your assigned hostel ({warden_hostel.name}).")
                            return redirect("inventory:room_changes")

                    # Gender Compatibility Check: Target hostel gender must match student's current hostel/gender
                    req_hostel_gender = req_obj.current_bed.room.block.hostel.gender_type
                    target_hostel_gender = target_bed.room.block.hostel.gender_type
                    if target_hostel_gender != "C" and req_hostel_gender != "C" and target_hostel_gender != req_hostel_gender:
                        messages.error(request, f"Gender Mismatch Violation: Cannot allocate {target_bed.room.block.hostel.get_gender_type_display()} bed to a student in {req_obj.current_bed.room.block.hostel.get_gender_type_display()} hostel.")
                        return redirect("inventory:room_changes")

                    # Release old bed
                    old_bed = req_obj.current_bed
                    old_bed.status = "AVAILABLE"
                    old_bed.occupant_name = ""
                    old_bed.occupant_student_id = ""
                    old_bed.save()

                    # Occupy new bed
                    target_bed.status = "OCCUPIED"
                    target_bed.occupant_name = req_obj.student_name
                    target_bed.occupant_student_id = req_obj.student_id
                    target_bed.save()

                req_obj.status = "APPROVED"
                req_obj.warden_remarks = remarks
                reviewer_label = f"Warden ({warden_hostel.name})" if warden_hostel else ("System Administrator" if is_admin else "Hostel Warden")
                req_obj.reviewed_by = reviewer_label
                req_obj.reviewed_at = timezone.now()
                req_obj.allocated_new_bed = target_bed
                req_obj.save()

                # Synchronize with AllocationAssignment and AllocationLetter so official records update
                from apps.allocation.models import AllocationAssignment
                from apps.publication.models import AllocationLetter
                assignments = AllocationAssignment.objects.filter(application__student_id=req_obj.student_id)
                for assign in assignments:
                    assign.bed = target_bed
                    assign.explanation = f"Room transfer approved by {reviewer_label}. Reallocated to {target_bed.room.block.hostel.name} Room {target_bed.room.room_number} (Bed {target_bed.bed_identifier}). Reason: {remarks}"
                    assign.save(update_fields=["bed", "explanation"])

                    letter = AllocationLetter.objects.filter(assignment=assign).first()
                    if letter:
                        letter.document_reference = f"AL-{assign.draft.cycle.code}-{target_bed.room.block.hostel.code}-{req_obj.student_id}"
                        letter.save(update_fields=["document_reference"])

                AuditEntry.objects.create(
                    actor_email=request.user.email or "warden@university.edu",
                    action="ROOM_CHANGE_APPROVED",
                    target_entity="RoomChangeRequest",
                    target_id=str(req_obj.id),
                    reason=f"Approved room transfer for {req_obj.student_name}. Reason: {remarks}"
                )
                messages.success(request, f"Approved room change for {req_obj.student_name}.")

            else:
                req_obj.status = "REJECTED"
                req_obj.warden_remarks = remarks
                reviewer_label = f"Warden ({warden_hostel.name})" if warden_hostel else ("System Administrator" if is_admin else "Hostel Warden")
                req_obj.reviewed_by = reviewer_label
                req_obj.reviewed_at = timezone.now()
                req_obj.save()

                AuditEntry.objects.create(
                    actor_email=request.user.email or "warden@university.edu",
                    action="ROOM_CHANGE_REJECTED",
                    target_entity="RoomChangeRequest",
                    target_id=str(req_obj.id),
                    reason=f"Rejected room change for {req_obj.student_name}. Remarks: {remarks}"
                )
                messages.info(request, f"Rejected room change request for {req_obj.student_name}.")

            return redirect("inventory:room_changes")

    # 2. Scope Request Queue by Warden Range
    requests_qs = RoomChangeRequest.objects.select_related(
        "current_bed", "current_bed__room", "current_bed__room__block__hostel", "allocated_new_bed"
    ).all().order_by("-created_at")

    if warden_hostel and not is_admin:
        # Wardens strictly see change requests from students allocated in their assigned hostel
        requests_qs = requests_qs.filter(current_bed__room__block__hostel=warden_hostel)

    requests_list = list(requests_qs)

    # 3. Available Bed Recommendations Scoped by Warden Range and Gender
    available_beds_qs = Bed.objects.filter(status="AVAILABLE").select_related("room", "room__block", "room__block__hostel")
    
    if warden_hostel and not is_admin:
        # Strictly within Warden's assigned hostel range and gender
        available_beds_qs = available_beds_qs.filter(
            room__block__hostel=warden_hostel,
            room__block__hostel__gender_type=warden_hostel.gender_type
        )
    
    available_beds = list(available_beds_qs[:50])

    sample_occupied_beds_qs = Bed.objects.filter(status="OCCUPIED").select_related("room", "room__block", "room__block__hostel")
    if warden_hostel and not is_admin:
        sample_occupied_beds_qs = sample_occupied_beds_qs.filter(room__block__hostel=warden_hostel)
    sample_occupied_beds = list(sample_occupied_beds_qs[:20])

    # If current user is student, attempt to find their application and occupied bed
    student_assigned_bed = None
    student_app = None
    if user.is_authenticated:
        from apps.allocation.models import AllocationAssignment
        # 1. Resolve Application
        student_app = getattr(user, "student_application", None)
        if not student_app:
            student_app = Application.objects.filter(
                Q(user=user) |
                Q(student_id=user.username) |
                Q(student_email__iexact=user.email)
            ).first()

        # 2. Resolve Current Assigned Bed
        student_id_val = student_app.student_id if student_app else user.username
        student_name_val = student_app.student_name if student_app else user.get_full_name()

        student_assigned_bed = Bed.objects.filter(
            Q(occupant_student_id=student_id_val) |
            Q(occupant_name__iexact=student_name_val)
        ).select_related("room", "room__block", "room__block__hostel").first()

        if not student_assigned_bed and student_app:
            assignment = AllocationAssignment.objects.filter(
                application=student_app
            ).select_related("bed", "bed__room", "bed__room__block", "bed__room__block__hostel").order_by("-created_at").first()
            if assignment:
                student_assigned_bed = assignment.bed

    context = {
        "requests": requests_list,
        "available_beds": available_beds,
        "sample_occupied_beds": sample_occupied_beds,
        "student_assigned_bed": student_assigned_bed,
        "student_app": student_app,
        "warden_hostel": warden_hostel,
    }
    return render(request, "inventory/room_changes.html", context)
