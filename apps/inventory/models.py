from django.db import models
from django.conf import settings
from apps.core.models import TenantModel

class Hostel(TenantModel):
    GENDER_CHOICES = [
        ("M", "Men"),
        ("W", "Women"),
        ("C", "Co-ed"),
    ]
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True)
    gender_type = models.CharField(max_length=2, choices=GENDER_CHOICES)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class WardenHostelAssignment(TenantModel):
    """
    9A: Final Role Model & Hostel Ownership.
    System Administrator assigns one Warden to one hostel.
    A Warden can manage only the hostel assigned to that Warden.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="warden_assignments",
        null=True,
        blank=True
    )
    warden_name = models.CharField(max_length=120)
    warden_email = models.EmailField()
    hostel = models.OneToOneField(
        Hostel,
        on_delete=models.CASCADE,
        related_name="warden_assignment"
    )
    assigned_by = models.CharField(max_length=120, default="System Administrator")
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.warden_name} ({self.warden_email}) -> {self.hostel.name}"


class Block(TenantModel):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name="blocks")
    name = models.CharField(max_length=80)
    code = models.CharField(max_length=20)
    number_of_floors = models.PositiveIntegerField(default=3)

    class Meta:
        unique_together = ("hostel", "code")

    def __str__(self):
        return f"{self.hostel.code} - {self.name}"


class Floor(TenantModel):
    """
    9B: Explicit Floor level in Hostel -> Block -> Floor -> Room -> Bed hierarchy.
    """
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="floors")
    floor_number = models.IntegerField(default=0, help_text="0=Ground, 1=1st Floor, etc.")
    name = models.CharField(max_length=60, blank=True, help_text="e.g. Ground Floor, 1st Floor")

    class Meta:
        unique_together = ("block", "floor_number")
        ordering = ["floor_number"]

    def __str__(self):
        return f"{self.block} - {self.name or f'Floor {self.floor_number}'}"


class Room(TenantModel):
    ROOM_TYPE_CHOICES = [
        ("SINGLE", "Single Occupancy"),
        ("DOUBLE", "Double Sharing"),
        ("TRIPLE", "Triple Sharing"),
        ("DORM", "Dormitory (4+)"),
    ]
    COOLING_CHOICES = [
        ("AC", "Air Conditioned (AC)"),
        ("COOLER", "Desert / Air Cooler"),
        ("NONE", "Natural / Ceiling Fan Only"),
    ]

    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="rooms")
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name="rooms", null=True, blank=True)
    room_number = models.CharField(max_length=20)
    floor_number = models.IntegerField(default=0)
    room_type = models.CharField(max_length=10, choices=ROOM_TYPE_CHOICES, default="DOUBLE")
    cooling_type = models.CharField(max_length=10, choices=COOLING_CHOICES, default="COOLER")
    capacity = models.PositiveIntegerField(default=2, help_text="Nominal capacity; derived from beds count")
    has_attached_washroom = models.BooleanField(default=False)
    has_ac = models.BooleanField(default=False)
    is_accessible = models.BooleanField(default=False, help_text="Wheelchair/accessible ground floor access")
    facilities = models.CharField(max_length=255, blank=True, default="Study Table, Wardrobe, High-Speed Wi-Fi")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("block", "room_number")

    def __str__(self):
        return f"Room {self.room_number} ({self.block})"

    @property
    def bed_capacity(self):
        """
        9B: Room capacity is derived from its bed records rather than assuming fixed capacity.
        """
        actual_beds = self.beds.count()
        return actual_beds if actual_beds > 0 else self.capacity

    @property
    def occupied_bed_count(self):
        return self.beds.filter(status__in=["OCCUPIED", "RESERVED"]).count()

    @property
    def available_bed_count(self):
        return self.beds.filter(status="AVAILABLE").count()


class Bed(TenantModel):
    BED_STATUS_CHOICES = [
        ("AVAILABLE", "Available"),
        ("RESERVED", "Reserved"),
        ("OCCUPIED", "Occupied"),
        ("MAINTENANCE", "Under Maintenance"),
    ]
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="beds")
    bed_identifier = models.CharField(max_length=10, help_text="e.g. A, B, C or 1, 2")
    status = models.CharField(max_length=20, choices=BED_STATUS_CHOICES, default="AVAILABLE")
    is_accessible = models.BooleanField(default=False)
    occupant_name = models.CharField(max_length=120, blank=True, help_text="Cached name for display")
    occupant_student_id = models.CharField(max_length=64, blank=True)

    class Meta:
        unique_together = ("room", "bed_identifier")

    def __str__(self):
        return f"{self.room} - Bed {self.bed_identifier}"


class RoomChangeRequest(TenantModel):
    """
    9E & 13 (Figure 5): Room Change Request Flow.
    Student submits request with reason & preferred room/cooling type.
    Warden reviews, approves, or rejects.
    Approved request reassigns bed and updates audit logs.
    """
    STATUS_CHOICES = [
        ("PENDING", "Pending Warden Review"),
        ("APPROVED", "Approved & Reassigned"),
        ("REJECTED", "Rejected"),
    ]

    student_id = models.CharField(max_length=64, db_index=True)
    student_name = models.CharField(max_length=120)
    student_email = models.EmailField()
    current_bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="change_requests_from")
    requested_hostel = models.ForeignKey(Hostel, on_delete=models.SET_NULL, null=True, blank=True)
    preferred_cooling = models.CharField(max_length=10, choices=Room.COOLING_CHOICES, default="AC")
    preferred_room_type = models.CharField(max_length=10, choices=Room.ROOM_TYPE_CHOICES, default="DOUBLE")
    reason = models.TextField(help_text="Detailed student justification for room transfer")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    warden_remarks = models.TextField(blank=True)
    reviewed_by = models.CharField(max_length=120, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    allocated_new_bed = models.ForeignKey(
        Bed,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="change_requests_to"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Room Change: {self.student_name} ({self.get_status_display()})"
