from django.test import TestCase
from apps.allocation.engine import AllocationEngine, ApplicantData, BedData

class PurePythonAllocationEngineTest(TestCase):
    def test_pure_python_allocation_heuristic(self):
        engine = AllocationEngine(random_seed=123)
        
        applicants = [
            ApplicantData(
                application_id="app_1",
                student_id="STU001",
                gender="M",
                requires_accessible=False,
                preferences=[("hostel_a", "SINGLE")]
            ),
            ApplicantData(
                application_id="app_2",
                student_id="STU002",
                gender="W",
                requires_accessible=True,
                preferences=[("hostel_b", "DOUBLE")]
            )
        ]
        
        beds = [
            BedData(
                bed_id="bed_1",
                hostel_id="hostel_a",
                hostel_gender="M",
                room_id="room_1",
                room_type="SINGLE",
                is_accessible=False,
                room_capacity=1
            ),
            BedData(
                bed_id="bed_2",
                hostel_id="hostel_b",
                hostel_gender="W",
                room_id="room_2",
                room_type="DOUBLE",
                is_accessible=True,
                room_capacity=2
            )
        ]

        result = engine.solve(applicants, beds)
        self.assertEqual(len(result.assignments), 2)
        self.assertEqual(len(result.unassigned_applications), 0)
        
        assigned_bed_ids = {a.bed_id for a in result.assignments}
        self.assertIn("bed_1", assigned_bed_ids)
        self.assertIn("bed_2", assigned_bed_ids)
