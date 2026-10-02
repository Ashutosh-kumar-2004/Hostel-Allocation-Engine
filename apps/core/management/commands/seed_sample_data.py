import hashlib
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.inventory.models import Hostel, Block, Floor, Room, Bed, WardenHostelAssignment, RoomChangeRequest
from apps.applications.models import AllocationCycle, Application
from apps.preferences.models import Preference, RoommateRequest
from apps.eligibility.models import EligibilityRule
from apps.allocation.models import AllocationDraft, AllocationAssignment
from apps.review.models import WardenApproval
from apps.publication.models import PublicationRecord, AllocationLetter
from apps.waitlist.models import WaitlistEntry
from apps.audit.models import AuditEntry

User = get_user_model()

class Command(BaseCommand):
    help = "Seeds comprehensive demonstrator data according to P03 Specification v2.0."

    def handle(self, *args, **options):
        self.stdout.write("Seeding comprehensive P03 v2.0 hostel allocation data...")

        # 1. Superuser / Admin & Wardens
        # 1a. System Administrator (admin / admin123)
        admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@university.edu", "first_name": "System", "last_name": "Administrator"}
        )
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.email = "admin@university.edu"
        admin_user.set_password("admin123")
        admin_user.save()

        # 1b. Hostel Warden for BH-4 (warden / warden123)
        warden_user, _ = User.objects.get_or_create(
            username="warden",
            defaults={"email": "warden@university.edu", "first_name": "Hostel Warden", "last_name": "(BH-4)"}
        )
        warden_user.is_staff = True
        warden_user.email = "warden@university.edu"
        warden_user.set_password("warden123")
        warden_user.save()

        # 1c. Secondary Hostel Warden for BH-1 (rajesh.warden / warden123)
        rajesh_user, _ = User.objects.get_or_create(
            username="rajesh.warden",
            defaults={"email": "rajesh.warden@university.edu", "first_name": "Dr. Rajesh", "last_name": "Sharma"}
        )
        rajesh_user.is_staff = True
        rajesh_user.email = "rajesh.warden@university.edu"
        rajesh_user.set_password("warden123")
        rajesh_user.save()

        # 2. Hostels (BH-4 Boys Residence, BH-1 Boys Residence, GH-1 Girls Residence)
        h_bh4, _ = Hostel.objects.get_or_create(
            code="BH-4",
            defaults={
                "name": "Hostel H-4 (Boys Residence)",
                "gender_type": "M",
                "description": "Senior undergraduate residence with study lounges and Wi-Fi.",
                "address": "North Campus Engineering Enclave"
            }
        )

        h_bh1, _ = Hostel.objects.get_or_create(
            code="BH-1",
            defaults={
                "name": "Hostel H-1 (BH-1 Boys Residence)",
                "gender_type": "M",
                "description": "Junior undergraduate residence with gymnasium and recreational rooms.",
                "address": "North Campus Science Quad"
            }
        )

        h_gh1, _ = Hostel.objects.get_or_create(
            code="GH-1",
            defaults={
                "name": "Gargi Hall of Residence (Girls)",
                "gender_type": "W",
                "description": "Undergraduate residence with 24/7 security and reading halls.",
                "address": "South Campus Residential Quad"
            }
        )

        # 3. Warden Assignments (1 Warden to 1 Hostel persistent mapping)
        w_assign_bh4, _ = WardenHostelAssignment.objects.update_or_create(
            hostel=h_bh4,
            defaults={
                "user": warden_user,
                "warden_name": "Hostel Warden (BH-4)",
                "warden_email": "warden@university.edu",
                "assigned_by": "System Administrator",
                "notes": "Appointed Warden for Hostel H-4 (Academic Year 2026-27)"
            }
        )

        w_assign_bh1, _ = WardenHostelAssignment.objects.update_or_create(
            hostel=h_bh1,
            defaults={
                "user": rajesh_user,
                "warden_name": "Dr. Rajesh Sharma",
                "warden_email": "rajesh.warden@university.edu",
                "assigned_by": "System Administrator",
                "notes": "Appointed Warden for Hostel H-1 (Academic Year 2026-27)"
            }
        )

        WardenHostelAssignment.objects.update_or_create(
            hostel=h_gh1,
            defaults={
                "warden_name": "Dr. Sunita Rao",
                "warden_email": "sunita.warden@university.edu",
                "assigned_by": "System Administrator",
                "notes": "Appointed Warden for Gargi Hall (Academic Year 2026-27)"
            }
        )

        # 4. Blocks & Floors
        b_bh4_a, _ = Block.objects.get_or_create(hostel=h_bh4, code="A", defaults={"name": "Block A", "number_of_floors": 3})
        b_bh1_a, _ = Block.objects.get_or_create(hostel=h_bh1, code="A", defaults={"name": "Block A", "number_of_floors": 3})
        b_gh1_a, _ = Block.objects.get_or_create(hostel=h_gh1, code="A", defaults={"name": "Block A", "number_of_floors": 3})

        fl_bh4_0, _ = Floor.objects.get_or_create(block=b_bh4_a, floor_number=0, defaults={"name": "Ground Floor"})
        fl_bh4_1, _ = Floor.objects.get_or_create(block=b_bh4_a, floor_number=1, defaults={"name": "First Floor"})
        fl_bh4_2, _ = Floor.objects.get_or_create(block=b_bh4_a, floor_number=2, defaults={"name": "Second Floor"})

        fl_bh1_0, _ = Floor.objects.get_or_create(block=b_bh1_a, floor_number=0, defaults={"name": "Ground Floor"})
        fl_bh1_1, _ = Floor.objects.get_or_create(block=b_bh1_a, floor_number=1, defaults={"name": "First Floor"})

        fl_gh1_0, _ = Floor.objects.get_or_create(block=b_gh1_a, floor_number=0, defaults={"name": "Ground Floor"})
        fl_gh1_1, _ = Floor.objects.get_or_create(block=b_gh1_a, floor_number=1, defaults={"name": "First Floor"})

        # 5. Rooms & Beds in BH-4
        # Room A-102 (4 beds, AC)
        r_102, _ = Room.objects.get_or_create(
            block=b_bh4_a,
            room_number="102",
            defaults={
                "floor": fl_bh4_1,
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

        # Room A-103 (6 beds, Cooler)
        r_103, _ = Room.objects.get_or_create(
            block=b_bh4_a,
            room_number="103",
            defaults={
                "floor": fl_bh4_1,
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
            block=b_bh4_a,
            room_number="001",
            defaults={
                "floor": fl_bh4_0,
                "floor_number": 0,
                "room_type": "DOUBLE",
                "cooling_type": "AC",
                "has_ac": True,
                "capacity": 2,
                "facilities": "Wheelchair Ramp, Wide Doorways, Accessible Bath, AC",
                "is_accessible": True
            }
        )
        for b_id in ("A", "B"):
            Bed.objects.get_or_create(room=r_001, bed_identifier=b_id, defaults={"status": "AVAILABLE"})

        # Rooms in BH-1
        r_bh1_101, _ = Room.objects.get_or_create(
            block=b_bh1_a,
            room_number="101",
            defaults={
                "floor": fl_bh1_1,
                "floor_number": 1,
                "room_type": "DOUBLE",
                "cooling_type": "COOLER",
                "capacity": 2,
                "facilities": "Window Cooler, Wardrobes, Study Tables",
                "is_accessible": False
            }
        )
        for b_id in ("A", "B"):
            Bed.objects.get_or_create(room=r_bh1_101, bed_identifier=b_id, defaults={"status": "AVAILABLE"})

        # Rooms in GH-1 (Gargi Girls Residence)
        r_gh1_101, _ = Room.objects.get_or_create(
            block=b_gh1_a,
            room_number="101",
            defaults={
                "floor": fl_gh1_1,
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
            Bed.objects.get_or_create(room=r_gh1_101, bed_identifier=b_id, defaults={"status": "AVAILABLE"})

        r_gh1_102, _ = Room.objects.get_or_create(
            block=b_gh1_a,
            room_number="102",
            defaults={
                "floor": fl_gh1_1,
                "floor_number": 1,
                "room_type": "TRIPLE",
                "cooling_type": "COOLER",
                "capacity": 3,
                "facilities": "Window Cooler, Study Desks",
                "is_accessible": False
            }
        )
        for b_id in ("A", "B", "C"):
            Bed.objects.get_or_create(room=r_gh1_102, bed_identifier=b_id, defaults={"status": "AVAILABLE"})

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

        # 8. Sample Demonstrator Students (README Table)
        # Format: (student_id, name, email, gender, is_accessible, cool_pref, room_pref, roommate_id, status)
        sample_students = [
            ("12300001", "Aarav Sharma", "aarav@university.edu", "M", False, "AC", "DORM", "12300002", "ALLOCATED"),
            ("12300002", "Rohan Verma", "rohan@university.edu", "M", False, "COOLER", "DORM", "12300001", "ALLOCATED"),
            ("12300003", "Kabir Mehta", "kabir@university.edu", "M", True, "AC", "DOUBLE", None, "ALLOCATED"),
            ("12300004", "Ananya Iyer", "ananya@university.edu", "W", False, "AC", "DOUBLE", "12300005", "ALLOCATED"),
            ("12300005", "Diya Patel", "diya@university.edu", "W", False, "COOLER", "TRIPLE", "12300004", "ALLOCATED"),
            ("12300030", "Gaurav Kumar", "gaurav.12300030@university.edu", "M", True, "AC", "DOUBLE", None, "WAITLISTED"),
            ("12300901", "Ashutosh Yadav", "ashutoshyadav202004@gmail.com", "M", False, "AC", "DORM", None, "ALLOCATED"),
        ]

        app_map = {}
        for s_id, name, email, gender, is_acc, cool_pref, room_pref, roommate_id, stu_status in sample_students:
            name_parts = name.split()
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

            stu_user, _ = User.objects.get_or_create(
                username=s_id,
                defaults={"email": email, "first_name": first_name, "last_name": last_name, "is_staff": False}
            )
            stu_user.email = email
            stu_user.first_name = first_name
            stu_user.last_name = last_name
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
                    "status": stu_status
                }
            )
            if not app.user:
                app.user = stu_user
            app.status = stu_status
            app.save(update_fields=["user", "status", "updated_at"])
            app_map[s_id] = app

            # Target hostel for preference
            target_hostel = h_gh1 if gender == "W" else h_bh4
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

        # Bilateral Roommate Handshake Confirmation (12300001 <-> 12300002)
        if "12300001" in app_map and "12300002" in app_map:
            RoommateRequest.objects.get_or_create(
                requester=app_map["12300001"],
                target=app_map["12300002"],
                defaults={"status": "ACCEPTED"}
            )
            RoommateRequest.objects.get_or_create(
                requester=app_map["12300002"],
                target=app_map["12300001"],
                defaults={"status": "ACCEPTED"}
            )

        # 9. Draft Allocation & Assignments
        draft, _ = AllocationDraft.objects.get_or_create(
            cycle=cycle,
            run_identifier="RUN-AY26-001",
            defaults={
                "random_seed": 42,
                "status": "PUBLISHED",
                "total_applicants": len(sample_students),
                "assigned_count": 6,
                "unassigned_count": 1
            }
        )
        if draft.status != "PUBLISHED":
            draft.status = "PUBLISHED"
            draft.save(update_fields=["status", "updated_at"])

        # Assign beds to the allocated applicants
        allocated_ids = ["12300001", "12300002", "12300003", "12300004", "12300005", "12300901"]
        for s_id in allocated_ids:
            app = app_map.get(s_id)
            if not app:
                continue

            existing_assign = AllocationAssignment.objects.filter(draft=draft, application=app).first()
            if not existing_assign:
                # Find suitable available bed
                target_gender = app.gender
                beds_qs = Bed.objects.filter(
                    status="AVAILABLE",
                    room__block__hostel__gender_type=target_gender
                )
                if app.requires_accessible_room:
                    bed = beds_qs.filter(room__is_accessible=True).first()
                else:
                    bed = beds_qs.filter(room__is_accessible=False).first()

                if not bed:
                    bed = Bed.objects.filter(status="AVAILABLE").first()

                if bed:
                    bed.status = "OCCUPIED"
                    bed.occupant_name = app.student_name
                    bed.occupant_student_id = app.student_id
                    bed.save()

                    existing_assign, _ = AllocationAssignment.objects.get_or_create(
                        draft=draft,
                        application=app,
                        defaults={
                            "bed": bed,
                            "preference_rank_honoured": 1,
                            "compatibility_score": 0.92,
                            "explanation": f"Honoured Rank #1 preference for {bed.room.block.hostel.name} ({bed.room.room_number}-{bed.bed_identifier})."
                        }
                    )

        # 10. Room Change Request for Rohan Verma (12300002)
        rohan_assign = AllocationAssignment.objects.filter(draft=draft, application__student_id="12300002").first()
        rohan_bed = rohan_assign.bed if rohan_assign else Bed.objects.filter(status="OCCUPIED").first()
        if rohan_bed:
            RoomChangeRequest.objects.get_or_create(
                student_id="12300002",
                defaults={
                    "student_name": "Rohan Verma",
                    "student_email": "rohan@university.edu",
                    "current_bed": rohan_bed,
                    "preferred_cooling": "AC",
                    "preferred_room_type": "DOUBLE",
                    "reason": "Requesting room transfer to an AC room due to chronic allergic dust reaction in non-AC block.",
                    "status": "PENDING"
                }
            )

        # 11. Waiting List Entry for Gaurav Kumar (12300030)
        app_waitlisted = app_map.get("12300030")
        if app_waitlisted:
            WaitlistEntry.objects.update_or_create(
                cycle=cycle,
                application=app_waitlisted,
                defaults={
                    "priority_order": 1,
                    "status": "ACTIVE"
                }
            )

        # 12. Warden Approval & Official Publication Record
        WardenApproval.objects.get_or_create(
            draft=draft,
            defaults={
                "warden_id": "warden",
                "warden_email": "warden@university.edu",
                "comments": "Approved allocation draft for Hostel H-4. Verified capacity and room constraints.",
                "is_approved": True
            }
        )

        PublicationRecord.objects.get_or_create(
            draft=draft,
            defaults={
                "published_by_id": "admin",
                "published_by_email": "admin@university.edu",
                "total_allocations": draft.assigned_count
            }
        )

        # Generate Allocation Letters with SHA-256 verification QR code for all assigned students
        for assign in AllocationAssignment.objects.filter(draft=draft).select_related("application", "bed", "bed__room", "bed__room__block", "bed__room__block__hostel"):
            hostel_code = assign.bed.room.block.hostel.code if assign.bed else "HST"
            ref = f"AL-{cycle.code}-{hostel_code}-{assign.application.student_id}"
            qr_code = hashlib.sha256(f"{ref}:{assign.id}".encode()).hexdigest()[:16].upper()

            AllocationLetter.objects.get_or_create(
                assignment=assign,
                defaults={
                    "document_reference": ref,
                    "qr_verification_code": qr_code,
                    "is_checked_in": False
                }
            )

        # 13. System Audit Log
        AuditEntry.objects.get_or_create(
            action="SYSTEM_INIT",
            target_entity="AllocationCycle",
            target_id=str(cycle.id),
            defaults={
                "actor_email": "admin@university.edu",
                "reason": "Initialized comprehensive P03 v2.0 demonstrator accounts, wardens, applicants, and publication letters."
            }
        )

        self.stdout.write(self.style.SUCCESS("Successfully seeded comprehensive P03 v2.0 data and credentials!"))
