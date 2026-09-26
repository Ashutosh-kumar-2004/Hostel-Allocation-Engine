from typing import List, Optional, Tuple
from django.db import transaction
from django.contrib.auth import get_user_model
from .models import Hostel, Block, Floor, Room, Bed, WardenHostelAssignment
from apps.audit.services import AuditService

User = get_user_model()

class InventoryService:
    """
    Domain service for Inventory management:
    - Hostels, Blocks, Floors, Rooms, and Beds CRUD
    - Scoped authorization (Admin university-wide, Warden strictly assigned hostel)
    - Safe deletion protection (cannot delete occupied or reserved inventory)
    - Full immutable audit trail recording
    """

    @staticmethod
    def get_available_beds_for_hostel(hostel_id: str) -> List[Bed]:
        return list(
            Bed.objects.filter(
                room__block__hostel_id=hostel_id,
                status="AVAILABLE",
                room__is_active=True,
                room__block__hostel__is_active=True
            ).select_related("room", "room__block", "room__block__hostel")
        )

    @staticmethod
    @transaction.atomic
    def reserve_bed(bed_id: str) -> Bed:
        bed = Bed.objects.select_for_update().get(id=bed_id)
        if bed.status != "AVAILABLE":
            raise ValueError(f"Bed {bed_id} is not available for reservation.")
        bed.status = "RESERVED"
        bed.save(update_fields=["status", "updated_at"])
        return bed

    @staticmethod
    @transaction.atomic
    def release_bed(bed_id: str) -> Bed:
        bed = Bed.objects.select_for_update().get(id=bed_id)
        bed.status = "AVAILABLE"
        bed.save(update_fields=["status", "updated_at"])
        return bed

    # =========================================================================
    # ADMIN POWER: CREATE HOSTEL
    # =========================================================================
    @staticmethod
    @transaction.atomic
    def create_hostel(
        code: str,
        name: str,
        gender_type: str = "M",
        description: str = "",
        address: str = "",
        actor_email: str = "admin@university.edu",
        actor_id: str = "admin",
        institution_id: str = "inst_default"
    ) -> Hostel:
        """
        Creates a new Hostel with default Block A and Ground Floor,
        making it immediately ready for room and bed provisioning.
        """
        code = code.strip().upper()
        if Hostel.objects.filter(code=code).exists():
            raise ValueError(f"A hostel with code '{code}' already exists.")

        hostel = Hostel.objects.create(
            code=code,
            name=name.strip(),
            gender_type=gender_type,
            description=description.strip(),
            address=address.strip(),
            is_active=True,
            institution_id=institution_id
        )

        # Automatically create default Block and Floor 0
        default_block = Block.objects.create(
            hostel=hostel,
            name="Block A",
            code="A",
            number_of_floors=3,
            institution_id=institution_id
        )
        Floor.objects.create(
            block=default_block,
            floor_number=0,
            name="Ground Floor",
            institution_id=institution_id
        )

        AuditService.record_action(
            action="HOSTEL_CREATED",
            target_entity="Hostel",
            target_id=str(hostel.id),
            actor_id=actor_id,
            actor_email=actor_email,
            reason=f"Administrator created new hostel '{hostel.name}' ({hostel.code}).",
            institution_id=institution_id
        )
        return hostel

    # =========================================================================
    # ADMIN POWER: CREATE & ASSIGN WARDEN
    # =========================================================================
    @staticmethod
    @transaction.atomic
    def create_and_assign_warden(
        hostel_id: str,
        warden_name: str,
        warden_email: str,
        username: str = "",
        password: str = "warden123",
        notes: str = "",
        actor_email: str = "admin@university.edu",
        actor_id: str = "admin",
        institution_id: str = "inst_default"
    ) -> WardenHostelAssignment:
        """
        Creates user account if needed and assigns Warden to target hostel (1-to-1).
        """
        hostel = Hostel.objects.get(id=hostel_id)
        warden_email = warden_email.strip().lower()
        if not username:
            username = warden_email.split("@")[0]

        user, user_created = User.objects.get_or_create(
            username=username,
            defaults={"email": warden_email, "first_name": warden_name, "is_staff": True}
        )
        if user_created:
            user.set_password(password or "warden123")
            user.save()
        elif not user.email:
            user.email = warden_email
            user.save(update_fields=["email"])

        assignment, created = WardenHostelAssignment.objects.update_or_create(
            hostel=hostel,
            defaults={
                "user": user,
                "warden_name": warden_name.strip(),
                "warden_email": warden_email,
                "assigned_by": actor_email,
                "notes": notes.strip(),
                "institution_id": institution_id
            }
        )

        AuditService.record_action(
            action="WARDEN_ASSIGNMENT_UPDATE",
            target_entity="WardenHostelAssignment",
            target_id=str(assignment.id),
            actor_id=actor_id,
            actor_email=actor_email,
            reason=f"Administrator assigned {warden_name} ({warden_email}) as Warden to {hostel.name}.",
            institution_id=institution_id
        )
        return assignment

    # =========================================================================
    # ADMIN & WARDEN: CREATE FLOOR
    # =========================================================================
    @staticmethod
    @transaction.atomic
    def create_floor(
        block_id: str,
        floor_number: int,
        name: str = "",
        actor_email: str = "",
        actor_id: str = "",
        user_hostel_scope: Optional[Hostel] = None,
        institution_id: str = "inst_default"
    ) -> Floor:
        block = Block.objects.select_related("hostel").get(id=block_id)
        if user_hostel_scope and block.hostel != user_hostel_scope:
            raise PermissionError(f"Permission Denied: You cannot add floors to {block.hostel.name}.")

        if not name:
            name = "Ground Floor" if floor_number == 0 else f"Floor {floor_number}"

        floor, created = Floor.objects.get_or_create(
            block=block,
            floor_number=floor_number,
            defaults={"name": name, "institution_id": institution_id}
        )
        if not created and name and floor.name != name:
            floor.name = name
            floor.save(update_fields=["name"])

        if block.number_of_floors < floor_number + 1:
            block.number_of_floors = floor_number + 1
            block.save(update_fields=["number_of_floors"])

        AuditService.record_action(
            action="FLOOR_CREATED",
            target_entity="Floor",
            target_id=str(floor.id),
            actor_id=actor_id,
            actor_email=actor_email,
            reason=f"Created/Updated {floor.name} in {block.name} ({block.hostel.name}).",
            institution_id=institution_id
        )
        return floor

    # =========================================================================
    # ADMIN & WARDEN: CREATE ROOM
    # =========================================================================
    @staticmethod
    @transaction.atomic
    def create_room(
        block_id: str,
        room_number: str,
        floor_number: int = 0,
        room_type: str = "DOUBLE",
        cooling_type: str = "COOLER",
        capacity: int = 2,
        is_accessible: bool = False,
        actor_email: str = "",
        actor_id: str = "",
        user_hostel_scope: Optional[Hostel] = None,
        institution_id: str = "inst_default"
    ) -> Room:
        """
        Creates Room and automatically creates its initial beds (A, B, C...).
        Warden can only create rooms in their assigned hostel.
        """
        block = Block.objects.select_related("hostel").get(id=block_id)
        if user_hostel_scope and block.hostel != user_hostel_scope:
            raise PermissionError(f"Permission Denied: You cannot add rooms to {block.hostel.name}.")

        room_number = room_number.strip().upper()
        if Room.objects.filter(block=block, room_number=room_number).exists():
            raise ValueError(f"Room '{room_number}' already exists in {block.name}.")

        # Ensure Floor exists
        floor, _ = Floor.objects.get_or_create(
            block=block,
            floor_number=floor_number,
            defaults={
                "name": "Ground Floor" if floor_number == 0 else f"Floor {floor_number}",
                "institution_id": institution_id
            }
        )

        room = Room.objects.create(
            block=block,
            floor=floor,
            room_number=room_number,
            floor_number=floor_number,
            room_type=room_type,
            cooling_type=cooling_type,
            capacity=capacity,
            has_ac=(cooling_type == "AC"),
            is_accessible=is_accessible or (floor_number == 0),
            is_active=True,
            institution_id=institution_id
        )

        # Auto-create beds (A, B, C, D...)
        bed_letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
        for i in range(min(capacity, len(bed_letters))):
            Bed.objects.create(
                room=room,
                bed_identifier=bed_letters[i],
                status="AVAILABLE",
                institution_id=institution_id
            )

        AuditService.record_action(
            action="ROOM_CREATED",
            target_entity="Room",
            target_id=str(room.id),
            actor_id=actor_id,
            actor_email=actor_email,
            reason=f"Added Room {room.room_number} ({room.get_room_type_display()}, {room.get_cooling_type_display()}, {capacity} beds) to {block.hostel.name} - {block.name}.",
            institution_id=institution_id
        )
        return room

    # =========================================================================
    # ADMIN & WARDEN: DELETE ROOM
    # =========================================================================
    @staticmethod
    @transaction.atomic
    def delete_room(
        room_id: str,
        actor_email: str = "",
        actor_id: str = "",
        user_hostel_scope: Optional[Hostel] = None,
        institution_id: str = "inst_default"
    ) -> bool:
        """
        Deletes room and its beds.
        SAFEGUARD: Fails if any bed is OCCUPIED or RESERVED.
        """
        room = Room.objects.select_related("block", "block__hostel").prefetch_related("beds").get(id=room_id)
        hostel = room.block.hostel

        if user_hostel_scope and hostel != user_hostel_scope:
            raise PermissionError(f"Permission Denied: You cannot delete rooms in {hostel.name}.")

        # Check occupancy safeguard
        occupied_beds = room.beds.filter(status__in=["OCCUPIED", "RESERVED"])
        if occupied_beds.exists():
            occ_list = ", ".join([f"Bed {b.bed_identifier} ({b.occupant_name or 'Active Resident'})" for b in occupied_beds])
            raise ValueError(f"Cannot delete Room {room.room_number}: Contains active resident allocations ({occ_list}). Reassign or check out residents first.")

        room_num = room.room_number
        hostel_name = hostel.name
        block_name = room.block.name

        # Delete beds then room
        room.beds.all().delete()
        room.delete()

        AuditService.record_action(
            action="ROOM_DELETED",
            target_entity="Room",
            target_id=str(room_id),
            actor_id=actor_id,
            actor_email=actor_email,
            reason=f"Deleted vacant Room {room_num} from {hostel_name} - {block_name}.",
            institution_id=institution_id
        )
        return True

    # =========================================================================
    # ADMIN & WARDEN: CREATE BED
    # =========================================================================
    @staticmethod
    @transaction.atomic
    def create_bed(
        room_id: str,
        bed_identifier: str = "",
        actor_email: str = "",
        actor_id: str = "",
        user_hostel_scope: Optional[Hostel] = None,
        institution_id: str = "inst_default"
    ) -> Bed:
        """
        Adds a new bed to a room.
        """
        room = Room.objects.select_related("block", "block__hostel").prefetch_related("beds").get(id=room_id)
        if user_hostel_scope and room.block.hostel != user_hostel_scope:
            raise PermissionError(f"Permission Denied: You cannot add beds to {room.block.hostel.name}.")

        existing_idents = set(room.beds.values_list("bed_identifier", flat=True))

        if not bed_identifier:
            for char in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]:
                if char not in existing_idents:
                    bed_identifier = char
                    break
            if not bed_identifier:
                bed_identifier = f"B{len(existing_idents) + 1}"
        else:
            bed_identifier = bed_identifier.strip().upper()
            if bed_identifier in existing_idents:
                raise ValueError(f"Bed '{bed_identifier}' already exists in Room {room.room_number}.")

        bed = Bed.objects.create(
            room=room,
            bed_identifier=bed_identifier,
            status="AVAILABLE",
            institution_id=institution_id
        )

        room.capacity = room.beds.count()
        room.save(update_fields=["capacity"])

        AuditService.record_action(
            action="BED_CREATED",
            target_entity="Bed",
            target_id=str(bed.id),
            actor_id=actor_id,
            actor_email=actor_email,
            reason=f"Added Bed {bed_identifier} to Room {room.room_number} in {room.block.hostel.name}.",
            institution_id=institution_id
        )
        return bed

    # =========================================================================
    # ADMIN & WARDEN: DELETE BED
    # =========================================================================
    @staticmethod
    @transaction.atomic
    def delete_bed(
        bed_id: str,
        actor_email: str = "",
        actor_id: str = "",
        user_hostel_scope: Optional[Hostel] = None,
        institution_id: str = "inst_default"
    ) -> bool:
        """
        Deletes a vacant bed from a room.
        SAFEGUARD: Fails if the bed is OCCUPIED or RESERVED.
        """
        bed = Bed.objects.select_related("room", "room__block", "room__block__hostel").get(id=bed_id)
        room = bed.room
        hostel = room.block.hostel

        if user_hostel_scope and hostel != user_hostel_scope:
            raise PermissionError(f"Permission Denied: You cannot delete beds in {hostel.name}.")

        if bed.status in ["OCCUPIED", "RESERVED"]:
            raise ValueError(f"Cannot delete Bed {bed.bed_identifier}: Bed is currently {bed.get_status_display()} by {bed.occupant_name or 'Resident'}.")

        bed_ident = bed.bed_identifier
        room_num = room.room_number
        hostel_name = hostel.name

        bed.delete()
        room.capacity = max(1, room.beds.count())
        room.save(update_fields=["capacity"])

        AuditService.record_action(
            action="BED_DELETED",
            target_entity="Bed",
            target_id=str(bed_id),
            actor_id=actor_id,
            actor_email=actor_email,
            reason=f"Deleted vacant Bed {bed_ident} from Room {room_num} in {hostel_name}.",
            institution_id=institution_id
        )
        return True
