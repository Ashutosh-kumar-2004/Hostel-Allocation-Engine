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
    bed_stats = Bed.objects.aggregate(
        total_beds=Count("id"),
        available_beds=Count("id", filter=Q(status="AVAILABLE")),
        occupied_beds=Count("id", filter=Q(status="OCCUPIED")),
        reserved_beds=Count("id", filter=Q(status="RESERVED")),
        maintenance_beds=Count("id", filter=Q(status="MAINTENANCE")),
    )
    total_hostels = Hostel.objects.filter(is_active=True).count()
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
            "total_beds": bed_stats.get("total_beds") or 0,
            "available_beds": bed_stats.get("available_beds") or 0,
            "occupied_beds": bed_stats.get("occupied_beds") or 0,
            "reserved_beds": bed_stats.get("reserved_beds") or 0,
            "maintenance_beds": bed_stats.get("maintenance_beds") or 0,
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
