from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.inventory.models import Hostel, Block, Floor, Room, Bed, WardenHostelAssignment, RoomChangeRequest
from apps.allocation.simulation import WhatIfSimulationService, SimulationApplicant, SimulationBed

User = get_user_model()

class P03V2SpecificationTests(TestCase):
    def setUp(self):
        self.hostel = Hostel.objects.create(
            name="Hostel H-4",
            code="BH-4",
            gender_type="M"
        )
        self.block = Block.objects.create(
            hostel=self.hostel,
            name="Block A",
            code="A"
        )
        self.floor = Floor.objects.create(
            block=self.block,
            floor_number=1,
            name="1st Floor"
        )

    def test_variable_room_capacity_derived_from_beds(self):
        # Room A-102 with 4 beds and AC
        room_102 = Room.objects.create(
            block=self.block,
            floor=self.floor,
            room_number="102",
            cooling_type="AC",
            capacity=4
        )
        for b_letter in ("A", "B", "C", "D"):
            Bed.objects.create(room=room_102, bed_identifier=b_letter)

        self.assertEqual(room_102.bed_capacity, 4)
        self.assertEqual(room_102.cooling_type, "AC")

        # Room A-103 with 6 beds and Cooler
        room_103 = Room.objects.create(
            block=self.block,
            floor=self.floor,
            room_number="103",
            cooling_type="COOLER",
            capacity=6
        )
        for b_num in ("1", "2", "3", "4", "5", "6"):
            Bed.objects.create(room=room_103, bed_identifier=b_num)

        self.assertEqual(room_103.bed_capacity, 6)
        self.assertEqual(room_103.cooling_type, "COOLER")

    def test_warden_single_hostel_ownership_uniqueness(self):
        assignment = WardenHostelAssignment.objects.create(
            hostel=self.hostel,
            warden_name="Dr. Rajesh Sharma",
            warden_email="rajesh@university.edu"
        )
        self.assertEqual(assignment.hostel.code, "BH-4")

        # Confirm 1-to-1: Creating another assignment for the same hostel raises IntegrityError
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            WardenHostelAssignment.objects.create(
                hostel=self.hostel,
                warden_name="Dr. Second Warden",
                warden_email="second@university.edu"
            )

    def test_what_if_simulation_isolation(self):
        sim_beds = [
            SimulationBed("b1", "BH-4", "M", "AC", "DOUBLE", False),
            SimulationBed("b2", "BH-4", "M", "COOLER", "DOUBLE", False),
        ]
        sim_apps = [
            SimulationApplicant("s1", "Aarav", "M", False, "BH-4", "AC", "DOUBLE"),
            SimulationApplicant("s2", "Rohan", "M", False, "BH-4", "COOLER", "DOUBLE"),
        ]
        result = WhatIfSimulationService.run_simulation(sim_apps, sim_beds)
        self.assertEqual(result.allocated_count, 2)
        self.assertEqual(result.waitlist_count, 0)
        self.assertEqual(result.preference_match_rate, 100.0)

    def test_role_context_processor(self):
        from apps.core.context_processors import user_roles
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser

        rf = RequestFactory()

        # 1. Anonymous visitor
        req_anon = rf.get("/")
        req_anon.user = AnonymousUser()
        roles_anon = user_roles(req_anon)
        self.assertTrue(roles_anon["is_guest"])
        self.assertFalse(roles_anon["is_student"])
        self.assertFalse(roles_anon["is_warden"])
        self.assertFalse(roles_anon["is_admin"])

        # 2. Student user
        student_user = User.objects.create_user(username="12345678", email="stu@test.edu", password="pass")
        req_stu = rf.get("/")
        req_stu.user = student_user
        roles_stu = user_roles(req_stu)
        self.assertTrue(roles_stu["is_student"])
        self.assertFalse(roles_stu["is_warden"])
        self.assertFalse(roles_stu["is_admin"])

        # 3. Warden user
        warden_user = User.objects.create_user(username="warden_user", email="warden@test.edu", password="pass")
        WardenHostelAssignment.objects.create(
            user=warden_user,
            warden_name="Test Warden",
            warden_email="warden@test.edu",
            hostel=self.hostel
        )
        req_warden = rf.get("/")
        req_warden.user = warden_user
        roles_warden = user_roles(req_warden)
        self.assertTrue(roles_warden["is_warden"])
        self.assertFalse(roles_warden["is_student"])
        self.assertFalse(roles_warden["is_admin"])

        # 4. Superuser admin
        admin_user = User.objects.create_user(username="admin_user", is_superuser=True, is_staff=True, password="pass")
        req_admin = rf.get("/")
        req_admin.user = admin_user
        roles_admin = user_roles(req_admin)
        self.assertTrue(roles_admin["is_admin"])
        self.assertFalse(roles_admin["is_student"])

