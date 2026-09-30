import os
import sys
import django
sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from apps.inventory.models import Hostel, Block, Floor, Room, Bed, WardenHostelAssignment
from apps.inventory.services import InventoryService
from apps.inventory.views import (
    create_hostel_view,
    admin_warden_assignments_view,
    create_floor_view,
    create_room_view,
    delete_room_view,
    create_bed_view,
    delete_bed_view,
)
from apps.audit.models import AuditEntry

User = get_user_model()
rf = RequestFactory()

def setup_request(req, user):
    req.user = user
    setattr(req, "session", {})
    messages = FallbackStorage(req)
    setattr(req, "_messages", messages)
    return req

def run_tests():
    print("--- STARTING COMPREHENSIVE INVENTORY CRUD & RBAC TEST ---")

    # 1. Clean up any previous test artifacts
    Hostel.objects.filter(code__in=["TEST-H1", "TEST-H2"]).delete()
    User.objects.filter(username__in=["test_admin_user", "test_warden_1", "test_warden_2"]).delete()

    admin_user = User.objects.create_superuser("test_admin_user", "admin@test.edu", "admin123")
    warden_user = User.objects.create_user("test_warden_1", "warden1@test.edu", "warden123")

    # -------------------------------------------------------------
    # TEST 1: Admin Power - Create New Hostel
    # -------------------------------------------------------------
    print("\n[TEST 1] Admin creates a new hostel TEST-H1...")
    req = rf.post("/inventory/hostels/create/", {
        "code": "TEST-H1",
        "name": "Test Hostel One",
        "gender_type": "M",
        "description": "Brand new boys hostel",
        "address": "Campus North",
    })
    setup_request(req, admin_user)
    resp = create_hostel_view(req)
    assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"

    hostel_1 = Hostel.objects.filter(code="TEST-H1").first()
    assert hostel_1 is not None, "Hostel TEST-H1 was not created!"
    assert hostel_1.blocks.count() == 1, "Block A should be auto-created!"
    block_1 = hostel_1.blocks.first()
    assert block_1.floors.count() == 1, "Ground Floor should be auto-created!"
    print(f"-> SUCCESS: Hostel {hostel_1.name} created with Block {block_1.name} and {block_1.floors.first().name}.")

    # Test that non-admin cannot create hostel
    req_unauth = rf.post("/inventory/hostels/create/", {
        "code": "FAIL-H",
        "name": "Unauthorized Hostel",
        "gender_type": "M"
    })
    setup_request(req_unauth, warden_user)
    resp_unauth = create_hostel_view(req_unauth)
    assert Hostel.objects.filter(code="FAIL-H").count() == 0, "Non-admin should not be able to create hostel!"
    print("-> SUCCESS: Non-admin creation blocked.")

    # -------------------------------------------------------------
    # TEST 2: Admin Power - Provision Warden with credentials & assignment
    # -------------------------------------------------------------
    print("\n[TEST 2] Admin provisions and assigns Warden to TEST-H1...")
    req = rf.post("/inventory/warden-assignments/", {
        "hostel_id": str(hostel_1.id),
        "warden_name": "Dr. Ramesh Warden",
        "warden_email": "ramesh.warden@university.edu",
        "username": "ramesh.warden",
        "password": "rameshpass123",
        "notes": "Assigned to Test Hostel One"
    })
    setup_request(req, admin_user)
    resp = admin_warden_assignments_view(req)
    assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"

    assignment = WardenHostelAssignment.objects.filter(hostel=hostel_1).first()
    assert assignment is not None, "WardenHostelAssignment not found!"
    assert assignment.warden_name == "Dr. Ramesh Warden"
    assert assignment.user is not None, "Linked User account was not created!"
    assert assignment.user.username == "ramesh.warden"
    assert assignment.user.check_password("rameshpass123"), "Password was not properly hashed/verified!"
    ramesh_warden_user = assignment.user
    print(f"-> SUCCESS: Warden user @{ramesh_warden_user.username} provisioned and mapped to {hostel_1.name}.")

    # -------------------------------------------------------------
    # TEST 3: Admin Power - Add Floor, Room, Bed in ANY hostel
    # -------------------------------------------------------------
    print("\n[TEST 3] Admin adds floor, room, and bed in TEST-H1...")
    # Add Floor 1
    req = rf.post("/inventory/floors/create/", {
        "block_id": str(block_1.id),
        "floor_number": 1,
        "name": "First Floor"
    })
    setup_request(req, admin_user)
    resp = create_floor_view(req)
    assert resp.status_code == 302
    assert Floor.objects.filter(block=block_1, floor_number=1).exists(), "Floor 1 not created!"

    # Add Room 101 (Double sharing, AC, 2 beds)
    req = rf.post("/inventory/rooms/create/", {
        "block_id": str(block_1.id),
        "floor_number": 1,
        "room_number": "101",
        "room_type": "DOUBLE",
        "cooling_type": "AC",
        "capacity": 2,
    })
    setup_request(req, admin_user)
    resp = create_room_view(req)
    assert resp.status_code == 302
    room_101 = Room.objects.filter(block=block_1, room_number="101").first()
    assert room_101 is not None, "Room 101 not created!"
    assert room_101.beds.count() == 2, f"Expected 2 beds in room 101, got {room_101.beds.count()}"
    bed_a, bed_b = room_101.beds.all()[:2]
    print(f"-> SUCCESS: Room {room_101.room_number} created with beds {[b.bed_identifier for b in room_101.beds.all()]}.")

    # Add 3rd bed (Bed C)
    req = rf.post("/inventory/beds/create/", {
        "room_id": str(room_101.id),
        "bed_identifier": "C"
    })
    setup_request(req, admin_user)
    resp = create_bed_view(req)
    assert resp.status_code == 302
    room_101.refresh_from_db()
    assert room_101.beds.count() == 3, f"Expected 3 beds after adding Bed C, got {room_101.beds.count()}"
    print("-> SUCCESS: Bed C added by Admin.")

    # -------------------------------------------------------------
    # TEST 4: Warden Power - Add Room & Bed in ASSIGNED hostel
    # -------------------------------------------------------------
    print("\n[TEST 4] Warden adds Room and Bed in ASSIGNED hostel TEST-H1...")
    req = rf.post("/inventory/rooms/create/", {
        "block_id": str(block_1.id),
        "floor_number": 0,
        "room_number": "G-01",
        "room_type": "SINGLE",
        "cooling_type": "COOLER",
        "capacity": 1,
    })
    setup_request(req, ramesh_warden_user)
    resp = create_room_view(req)
    assert resp.status_code == 302
    room_g01 = Room.objects.filter(block=block_1, room_number="G-01").first()
    assert room_g01 is not None, "Warden could not create room in assigned hostel!"
    assert room_g01.beds.count() == 1
    print(f"-> SUCCESS: Warden created Room {room_g01.room_number} with Bed A.")

    # Warden adds Bed B to G-01
    req = rf.post("/inventory/beds/create/", {
        "room_id": str(room_g01.id),
        "bed_identifier": "B"
    })
    setup_request(req, ramesh_warden_user)
    resp = create_bed_view(req)
    assert resp.status_code == 302
    room_g01.refresh_from_db()
    assert room_g01.beds.count() == 2
    print("-> SUCCESS: Warden added Bed B to Room G-01.")

    # -------------------------------------------------------------
    # TEST 5: Warden Isolation - Cross-hostel mutation BLOCKED
    # -------------------------------------------------------------
    print("\n[TEST 5] Warden cross-hostel boundary enforcement...")
    # Create another hostel TEST-H2
    hostel_2 = InventoryService.create_hostel("TEST-H2", "Test Hostel Two", "F")
    block_2 = hostel_2.blocks.first()

    # Warden Ramesh (assigned to TEST-H1) tries to add a room to TEST-H2
    try:
        InventoryService.create_room(
            block_id=str(block_2.id),
            room_number="201",
            user_hostel_scope=hostel_1  # Warden's assigned hostel
        )
        assert False, "Should have raised PermissionError for cross-hostel creation!"
    except PermissionError as e:
        print(f"-> SUCCESS: Blocked cross-hostel room creation: {e}")

    # Warden Ramesh tries to delete a room in TEST-H2
    room_in_h2 = InventoryService.create_room(
        block_id=str(block_2.id),
        room_number="202",
        capacity=1
    )
    try:
        InventoryService.delete_room(
            room_id=str(room_in_h2.id),
            user_hostel_scope=hostel_1
        )
        assert False, "Should have raised PermissionError for cross-hostel deletion!"
    except PermissionError as e:
        print(f"-> SUCCESS: Blocked cross-hostel room deletion: {e}")

    # -------------------------------------------------------------
    # TEST 6: Safe Deletion Safeguards (Occupied / Reserved Beds)
    # -------------------------------------------------------------
    print("\n[TEST 6] Deletion safeguards against occupied beds...")
    bed_to_occupy = room_101.beds.filter(bed_identifier="A").first()
    bed_to_occupy.status = "OCCUPIED"
    bed_to_occupy.occupant_name = "Aryan Sharma"
    bed_to_occupy.save()

    # Attempting to delete occupied bed must fail
    try:
        InventoryService.delete_bed(str(bed_to_occupy.id))
        assert False, "Should have raised ValueError when deleting occupied bed!"
    except ValueError as e:
        print(f"-> SUCCESS: Protected occupied bed from deletion: {e}")

    # Attempting to delete room with occupied bed must fail
    try:
        InventoryService.delete_room(str(room_101.id))
        assert False, "Should have raised ValueError when deleting room with occupied bed!"
    except ValueError as e:
        print(f"-> SUCCESS: Protected room with occupied bed from deletion: {e}")

    # -------------------------------------------------------------
    # TEST 7: Successful Safe Deletion of Vacant Bed & Vacant Room
    # -------------------------------------------------------------
    print("\n[TEST 7] Successful deletion of vacant bed & vacant room...")
    # Warden deletes vacant Bed B from G-01
    bed_b_g01 = room_g01.beds.filter(bed_identifier="B").first()
    req = rf.post(f"/inventory/beds/{bed_b_g01.id}/delete/")
    setup_request(req, ramesh_warden_user)
    resp = delete_bed_view(req, bed_id=bed_b_g01.id)
    assert resp.status_code == 302
    room_g01.refresh_from_db()
    assert room_g01.beds.count() == 1, "Vacant Bed B was not deleted!"
    print("-> SUCCESS: Vacant Bed B deleted by Warden.")

    # Warden deletes vacant Room G-01
    req = rf.post(f"/inventory/rooms/{room_g01.id}/delete/")
    setup_request(req, ramesh_warden_user)
    resp = delete_room_view(req, room_id=room_g01.id)
    assert resp.status_code == 302
    assert not Room.objects.filter(id=room_g01.id).exists(), "Vacant Room G-01 was not deleted!"
    print("-> SUCCESS: Vacant Room G-01 deleted by Warden.")

    # -------------------------------------------------------------
    # TEST 8: Immutable Audit Entries Verification
    # -------------------------------------------------------------
    print("\n[TEST 8] Verifying immutable AuditEntry records...")
    actions = AuditEntry.objects.filter(action__in=[
        "HOSTEL_CREATED", "WARDEN_ASSIGNMENT_UPDATE", "FLOOR_CREATED",
        "ROOM_CREATED", "BED_CREATED", "ROOM_DELETED", "BED_DELETED"
    ]).values_list("action", flat=True)

    required_actions = ["HOSTEL_CREATED", "WARDEN_ASSIGNMENT_UPDATE", "FLOOR_CREATED", "ROOM_CREATED", "BED_CREATED", "ROOM_DELETED", "BED_DELETED"]
    for act in required_actions:
        assert act in actions, f"Missing audit action {act}!"
        print(f"-> Audit verified for: {act}")

    # Cleanup
    Hostel.objects.filter(code__in=["TEST-H1", "TEST-H2"]).delete()
    User.objects.filter(username__in=["test_admin_user", "test_warden_1", "ramesh.warden"]).delete()

    print("\n=== ALL INVENTORY CRUD & RBAC TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_tests()
