from django.shortcuts import render
from django.db.models import Count, Q
from apps.inventory.models import Hostel, Bed, RoomChangeRequest, WardenHostelAssignment
from apps.applications.models import Application, AllocationCycle
from apps.allocation.models import AllocationDraft

def dashboard_view(request):
    """
    Renders the unified operational dashboard for Hostel Allocation.
    Displays live cycle status, quick stats, active role indicators, and system metrics.
    """
    total_hostels = Hostel.objects.filter(is_active=True).count()
    total_beds = Bed.objects.count()
    available_beds = Bed.objects.filter(status="AVAILABLE").count()
    occupied_beds = Bed.objects.filter(status="OCCUPIED").count()
    reserved_beds = Bed.objects.filter(status="RESERVED").count()
    maintenance_beds = Bed.objects.filter(status="MAINTENANCE").count()
    
    total_applications = Application.objects.count()
    pending_room_changes = RoomChangeRequest.objects.filter(status="PENDING").count()
    drafts_count = AllocationDraft.objects.count()
    wardens_count = WardenHostelAssignment.objects.count()

    current_cycle = AllocationCycle.objects.order_by("-created_at").first()

    context = {
        "title": "Hostel Allocation & Roommate Matching Engine",
        "current_cycle": current_cycle.name if current_cycle else "Academic Year 2026-2027 (Autumn Allotment)",
        "stats": {
            "total_hostels": total_hostels,
            "total_beds": total_beds,
            "available_beds": available_beds,
            "occupied_beds": occupied_beds,
            "reserved_beds": reserved_beds,
            "maintenance_beds": maintenance_beds,
            "pending_applications": total_applications,
            "draft_allocations": drafts_count,
            "pending_room_changes": pending_room_changes,
            "wardens_assigned": wardens_count,
        }
    }
    return render(request, "dashboard.html", context)


def architecture_docs_view(request):
    """
    Interactive documentation hub showing Figures 1 to 5, ERD, and Architecture Map.
    """
    return render(request, "docs/architecture.html")
