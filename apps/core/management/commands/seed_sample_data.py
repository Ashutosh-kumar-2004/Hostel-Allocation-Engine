from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from apps.inventory.models import Hostel, Block, Floor, Room, Bed, WardenHostelAssignment, RoomChangeRequest
from apps.applications.models import AllocationCycle, Application
from apps.preferences.models import Preference
from apps.eligibility.models import EligibilityRule
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.audit.models import AuditEntry

User = get_user_model()

class Command(BaseCommand):
    help = "Seeds comprehensive demonstrator data according to P03 Specification v2.0."

    def handle(self, *args, **options):
        self.stdout.write("Seeding comprehensive P03 v2.0 hostel allocation data...")

        # 1. Superuser / Admin & Wardens
        admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@university.edu", "is_staff": True, "is_superuser": True}
        )
        if not admin_user.has_usable_password():
            admin_user.set_password("admin123")
            admin_user.save()

        # 2. Hostels (H-4 Boys Hostel & Gargi Girls Hostel)
        h_men, _ = Hostel.objects.get_or_create(
            code="BH-4",
            defaults={
                "name": "Hostel H-4 (Boys Residence)",
                "gender_type": "M",
                "description": "Senior undergraduate residence with study lounges and Wi-Fi.",
                "address": "North Campus Engineering Enclave"
            }
        )

        h_women, _ = Hostel.objects.get_or_create(
            code="GH-1",
            defaults={
                "name": "Gargi Hall of Residence (Girls)",
                "gender_type": "W",
                "description": "Undergraduate residence with 24/7 security and reading halls.",
                "address": "South Campus Residential Quad"
            }
        )

        # 3. Warden Assignments (1 Warden to 1 Hostel persistent mapping)
        WardenHostelAssignment.objects.get_or_create(
            hostel=h_men,
            defaults={
                "warden_name": "Dr. Rajesh Sharma",
                "warden_email": "rajesh.warden@university.edu",
                "assigned_by": "System Administrator",
                "notes": "Appointed for Academic Year 2026-27"
            }
        )

        WardenHostelAssignment.objects.get_or_create(
            hostel=h_women,
            defaults={
                "warden_name": "Dr. Sunita Rao",
                "warden_email": "sunita.warden@university.edu",
                "assigned_by": "System Administrator",
                "notes": "Appointed for Academic Year 2026-27"
            }
        )

        # 4. Blocks & Floors
        b_men_a, _ = Block.objects.get_or_create(hostel=h_men, code="A", defaults={"name": "Block A", "number_of_floors": 3})
        b_women_a, _ = Block.objects.get_or_create(hostel=h_women, code="A", defaults={"name": "Block A", "number_of_floors": 3})

        fl_0, _ = Floor.objects.get_or_create(block=b_men_a, floor_number=0, defaults={"name": "Ground Floor"})
        fl_1, _ = Floor.objects.get_or_create(block=b_men_a, floor_number=1, defaults={"name": "First Floor"})
        fl_2, _ = Floor.objects.get_or_create(block=b_men_a, floor_number=2, defaults={"name": "Second Floor"})

        fl_w0, _ = Floor.objects.get_or_create(block=b_women_a, floor_number=0, defaults={"name": "Ground Floor"})
        fl_w1, _ = Floor.objects.get_or_create(block=b_women_a, floor_number=1, defaults={"name": "First Floor"})

        # 5. Rooms with Variable Capacities & Cooling Types (AC, Cooler, None)
        # Room A-102 (4 beds, AC) as per docx example
        r_102, _ = Room.objects.get_or_create(
            block=b_men_a,
            room_number="102",
            defaults={
                "floor": fl_1,
                "floor_number": 1,
                "room_type": "DORM",
                "cooling_type": "AC",
                "has_ac": True,
                "capacity": 4,
                "facilities": "Split Air Conditioner, Individual Study Desks, High-Speed Wi-Fi",
                "is_accessible": False
            }
        )
        for b_letter in ("A", "B", "C", "D"):
            Bed.objects.get_or_create(room=r_102, bed_identifier=b_letter, defaults={"status": "AVAILABLE"})

        # Room A-103 (6 beds, Cooler) as per docx example
        r_103, _ = Room.objects.get_or_create(
            block=b_men_a,
            room_number="103",
            defaults={
                "floor": fl_1,
                "floor_number": 1,
                "room_type": "DORM",
                "cooling_type": "COOLER",
                "capacity": 6,
                "facilities": "Desert Air Cooler, 6 Cupboards, Power Backup",
                "is_accessible": False
            }
        )
        for b_num in ("1", "2", "3", "4", "5", "6"):
            Bed.objects.get_or_create(room=r_103, bed_identifier=b_num, defaults={"status": "AVAILABLE"})

        # Ground Floor Accessible Room A-001 (2 beds, AC, Wheelchair Accessible)
        r_001, _ = Room.objects.get_or_create(
            block=b_men_a,
            room_number="001",
            defaults={
                "floor": fl_0,
                "floor_number": 0,
                "room_type": "DOUBLE",
                "cooling_type": "AC",
                "has_ac": True,
                "capacity": 2,
                "facilities": "Ground floor ramp, roll-in shower, AC, wide doorway",
                "is_accessible": True
            }
        )
        for b_id in ("A", "B"):
            Bed.objects.get_or_create(room=r_001, bed_identifier=b_id, defaults={"status": "AVAILABLE", "is_accessible": True})

        # Girls Hostel Rooms
        r_w101, _ = Room.objects.get_or_create(
            block=b_women_a,
            room_number="101",
            defaults={
                "floor": fl_w1,
                "floor_number": 1,
                "room_type": "DOUBLE",
                "cooling_type": "AC",
                "has_ac": True,
                "capacity": 2,
                "facilities": "Air Conditioner, Balcony, Attached Bath",
                "is_accessible": False
            }
        )
        for b_id in ("A", "B"):
            Bed.objects.get_or_create(room=r_w101, bed_identifier=b_id, defaults={"status": "AVAILABLE"})

        r_w102, _ = Room.objects.get_or_create(
            block=b_women_a,
            room_number="102",
            defaults={
                "floor": fl_w1,
                "floor_number": 1,
                "room_type": "TRIPLE",
                "cooling_type": "COOLER",
                "capacity": 3,
                "facilities": "Window Cooler, Study Desks",
                "is_accessible": False
            }
        )
        for b_id in ("A", "B", "C"):
            Bed.objects.get_or_create(room=r_w102, bed_identifier=b_id, defaults={"status": "AVAILABLE"})

        # 6. Allocation Cycle
        now = timezone.now()
        cycle, _ = AllocationCycle.objects.get_or_create(
            code="AY2026-AUTUMN",
            defaults={
                "name": "Academic Year 2026-2027 (Autumn Allotment)",
                "academic_year": "2026-27",
                "application_start": now - timedelta(days=15),
                "application_end": now + timedelta(days=10),
                "status": "OPEN",
                "description": "Standard annual undergraduate intake."
            }
        )

        # 7. Eligibility Rules
        EligibilityRule.objects.get_or_create(
            cycle=cycle,
            name="Minimum Distance Policy",
            defaults={"rule_type": "DISTANCE", "parameters": {"min_distance_km": 30}, "is_hard_rule": True}
        )
        EligibilityRule.objects.get_or_create(
            cycle=cycle,
            name="Minimum Academic CGPA",
            defaults={"rule_type": "ACADEMIC", "parameters": {"min_cgpa": 6.0}, "is_hard_rule": True}
        )
        EligibilityRule.objects.get_or_create(
            cycle=cycle,
            name="Disciplinary Clearance",
            defaults={"rule_type": "DISCIPLINARY", "parameters": {"max_infractions": 0}, "is_hard_rule": True}
        )
        EligibilityRule.objects.get_or_create(
            cycle=cycle,
            name="Fee Accounts Clearance",
            defaults={"rule_type": "FEE_CLEARED", "parameters": {"require_clearance": True}, "is_hard_rule": True}
        )

        # 8. Sample Students & Applications (Strict 123XXXXX format with Demonstrator Mutual Roommate Pairings)
        sample_students = [
            ("12300001", "Aarav Sharma", "aarav@university.edu", "M", False, "AC", "DORM", "12300002"),
            ("12300002", "Rohan Verma", "rohan@university.edu", "M", False, "COOLER", "DORM", "12300001"),
            ("12300003", "Kabir Mehta", "kabir@university.edu", "M", True, "AC", "DOUBLE", None),
            ("12300004", "Ananya Iyer", "ananya@university.edu", "W", False, "AC", "DOUBLE", "12300005"),
            ("12300005", "Diya Patel", "diya@university.edu", "W", False, "COOLER", "TRIPLE", "12300004"),
        ]

        apps = []
        for s_id, name, email, gender, is_acc, cool_pref, room_pref, roommate_id in sample_students:
            # Create student user account for direct authentication
            name_parts = name.split()
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            stu_user, _ = User.objects.get_or_create(
                username=s_id,
                defaults={"email": email, "first_name": first_name, "last_name": last_name, "is_staff": False}
            )
            if not stu_user.has_usable_password():
                stu_user.set_password("student123")
                stu_user.save()

            app, _ = Application.objects.get_or_create(
                cycle=cycle,
                student_id=s_id,
                defaults={
                    "user": stu_user,
                    "student_name": name,
                    "student_email": email,
                    "gender": gender,
                    "programme": "B.Tech Computer Science",
                    "requires_accessible_room": is_acc,
                    "distance_from_campus_km": 65.0,
                    "cgpa": 8.40,
                    "fee_cleared": True,
                    "has_disciplinary_record": False,
                    "status": "ALLOCATED"
                }
            )
            if not app.user:
                app.user = stu_user
                app.save(update_fields=["user"])

            apps.append((app, cool_pref, room_pref))
            # Ranked Preference
            target_hostel = h_men if gender == "M" else h_women
            pref, created = Preference.objects.get_or_create(
                application=app,
                rank=1,
                defaults={
                    "preferred_hostel": target_hostel, 
                    "preferred_room_type": room_pref,
                    "preferred_roommate_id": roommate_id
                }
            )
            if not created and roommate_id:
                pref.preferred_roommate_id = roommate_id
                pref.save(update_fields=["preferred_roommate_id", "updated_at"])

        # 9. Draft Allocation and Assignments (Demonstrator)
        draft, _ = AllocationDraft.objects.get_or_create(
            cycle=cycle,
            run_identifier="RUN-AY26-001",
            defaults={
                "random_seed": 42,
                "status": "COMPLETED",
                "total_applicants": len(sample_students),
                "assigned_count": len(sample_students),
                "unassigned_count": 0
            }
        )

        # Assign beds
        all_beds = list(Bed.objects.filter(status="AVAILABLE").select_related("room", "room__block", "room__block__hostel"))
        for app, cool_pref, room_pref in apps:
            chosen_bed = None
            for b in all_beds:
                if b.room.block.hostel.gender_type == app.gender:
                    if app.requires_accessible_room and not b.is_accessible:
                        continue
                    chosen_bed = b
                    all_beds.remove(b)
                    break

            if chosen_bed:
                chosen_bed.status = "OCCUPIED"
                chosen_bed.occupant_name = app.student_name
                chosen_bed.occupant_student_id = app.student_id
                chosen_bed.save()

                AllocationAssignment.objects.get_or_create(
                    draft=draft,
                    application=app,
                    defaults={
                        "bed": chosen_bed,
                        "preference_rank_honoured": 1,
                        "compatibility_score": 0.88,
                        "explanation": f"Honoured Rank #1 preference for {chosen_bed.room.block.hostel.name}. Matched {chosen_bed.room.cooling_type} cooling and room type {chosen_bed.room.room_type}."
                    }
                )

        # 10. Sample Room Change Request
        sample_bed = Bed.objects.filter(status="OCCUPIED").first()
        if sample_bed:
            RoomChangeRequest.objects.get_or_create(
                student_id="12300002",
                defaults={
                    "student_name": "Rohan Verma",
                    "student_email": "rohan@university.edu",
                    "current_bed": sample_bed,
                    "preferred_cooling": "AC",
                    "preferred_room_type": "DOUBLE",
                    "reason": "Requesting room transfer to an AC room due to chronic allergic dust reaction in non-AC block.",
                    "status": "PENDING"
                }
            )

        # 11. Initial Audit Entry
        AuditEntry.objects.get_or_create(
            action="SYSTEM_INIT",
            target_entity="AllocationCycle",
            target_id=str(cycle.id),
            defaults={
                "actor_email": "system@university.edu",
                "reason": "Initialized P03 v2.0 Demonstrator data with Hostels, Wardens, Variable Rooms, and Sample Draft."
            }
        )

        self.stdout.write(self.style.SUCCESS("Successfully seeded comprehensive P03 v2.0 data!"))
