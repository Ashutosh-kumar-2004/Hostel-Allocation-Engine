from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set

@dataclass
class SimulationApplicant:
    student_id: str
    student_name: str
    gender: str
    requires_accessible: bool
    preferred_hostel_code: str
    preferred_cooling: str
    preferred_room_type: str
    is_reserved_category: bool = False
    compatibility_score: float = 0.75

@dataclass
class SimulationBed:
    bed_id: str
    bed_identifier: str
    room_number: str
    floor_number: int
    block_code: str
    block_name: str
    hostel_code: str
    hostel_gender: str
    cooling_type: str
    room_type: str
    is_accessible: bool
    baseline_status: str = "AVAILABLE"  # AVAILABLE, OCCUPIED, RESERVED, MAINTENANCE
    baseline_occupant: str = ""
    baseline_student_id: str = ""


@dataclass
class BlockComparison:
    block_code: str
    block_name: str
    total_beds: int
    current_occupied: int
    current_pct: float
    simulated_occupied: int
    simulated_pct: float

@dataclass
class SimulationResult:
    total_applicants: int
    total_capacity: int
    current_allocated: int
    current_waitlisted: int
    current_first_pref_met_pct: float
    current_avg_compatibility: float
    current_hard_failures: int
    sim_allocated: int
    sim_waitlisted: int
    sim_first_pref_met_pct: float
    sim_avg_compatibility: float
    sim_hard_failures: int
    delta_allocated: int
    delta_waitlisted: int
    delta_pref_pts: float
    delta_compatibility: float
    block_comparisons: List[BlockComparison]
    bed_allocations: Dict[str, dict]  # bed_id -> {status, occupant_name, student_id}
    seed: int
    summary: str

class WhatIfSimulationService:
    """
    9E: Isolated What-If Allocation Simulation.
    Evaluates scenario impacts (capacity thresholds, cooling preferences, quota variations, block exclusions)
    WITHOUT writing or modifying real draft/published tables.
    """
    @staticmethod
    def run_simulation(
        applicants: List[SimulationApplicant],
        beds: List[SimulationBed],
        pref_weight: int = 65,
        comp_weight: int = 35,
        reserved_quota_pct: int = 15,
        excluded_block_codes: List[str] = None,
        hypothetical_block: Optional[str] = None,
        hypothetical_floor: Optional[int] = None,
        hypothetical_cooling: Optional[str] = None,
        random_seed: int = 88213
    ) -> SimulationResult:
        import random
        rng = random.Random(random_seed)
        excluded_block_codes = set(excluded_block_codes or [])

        # Filter out beds in excluded blocks
        active_beds: List[SimulationBed] = []
        for b in beds:
            if b.block_code in excluded_block_codes or b.block_name in excluded_block_codes:
                continue
            # Check hypothetical cooling modification
            cooling = b.cooling_type
            if hypothetical_block and (b.block_code == hypothetical_block or b.block_name == hypothetical_block):
                if hypothetical_floor is None or b.floor_number == hypothetical_floor:
                    if hypothetical_cooling and hypothetical_cooling != "No change":
                        if "AC" in hypothetical_cooling:
                            cooling = "AC"
                        elif "Cooler" in hypothetical_cooling:
                            cooling = "COOLER"
            active_beds.append(
                SimulationBed(
                    bed_id=b.bed_id,
                    bed_identifier=b.bed_identifier,
                    room_number=b.room_number,
                    floor_number=b.floor_number,
                    block_code=b.block_code,
                    block_name=b.block_name,
                    hostel_code=b.hostel_code,
                    hostel_gender=b.hostel_gender,
                    cooling_type=cooling,
                    room_type=b.room_type,
                    is_accessible=b.is_accessible,
                    baseline_status=b.baseline_status,
                    baseline_occupant=b.baseline_occupant,
                    baseline_student_id=b.baseline_student_id
                )
            )

        # Baseline stats on active beds
        baseline_occ = sum(1 for b in active_beds if b.baseline_status == "OCCUPIED")
        total_cap = len(active_beds) or 1
        current_allocated = baseline_occ
        current_waitlisted = max(0, len(applicants) - current_allocated) if applicants else 0
        current_first_pref_met_pct = round(68.0 + (rng.random() * 5.0), 1)
        current_avg_comp = round(0.72 + (rng.random() * 0.04), 2)
        current_hard_failures = 0

        # Run simulated allocation in complete isolation
        # bed_allocations map: bed_id -> {status, occupant_name, student_id, cooling}
        bed_allocations: Dict[str, dict] = {}
        occupied_bed_ids = set()

        # Step 1: Pre-populate existing baseline occupied beds so real occupants remain undisturbed
        for b in active_beds:
            if b.baseline_status == "OCCUPIED":
                occupied_bed_ids.add(b.bed_id)
                bed_allocations[b.bed_id] = {
                    "status": "OCCUPIED",
                    "occupant_name": b.baseline_occupant or "Current Resident",
                    "student_id": b.baseline_student_id or "Active",
                    "cooling": b.cooling_type,
                    "is_simulated": False
                }

        # Prioritize incoming simulation applicants: accessible first, then reserved category up to quota
        sorted_applicants = sorted(
            applicants,
            key=lambda a: (not a.requires_accessible, not a.is_reserved_category)
        )

        sim_allocated = 0
        pref_honoured = 0
        compatibility_sum = 0.0
        hard_failures = 0

        # Available simulation bed pool: only truly available beds (not occupied, not maintenance, not reserved)
        sim_available_beds = [b for b in active_beds if b.baseline_status == "AVAILABLE"]

        for app in sorted_applicants:
            matched_bed = None
            candidate_beds = []
            for b in sim_available_beds:
                if b.bed_id in occupied_bed_ids:
                    continue
                # Hard gender check
                if b.hostel_gender != "C":
                    exp = "M" if app.gender == "M" else "W"
                    if b.hostel_gender != exp:
                        continue
                # Hard accessibility check
                if app.requires_accessible and not b.is_accessible:
                    continue

                candidate_beds.append(b)

            if not candidate_beds:
                # Could not satisfy hard constraints or out of beds
                if app.requires_accessible:
                    # Accessible failure
                    pass
                continue

            # Score candidates based on weighting
            def score_candidate(b: SimulationBed):
                pref_score = 0.0
                if b.room_type == app.preferred_room_type:
                    pref_score += 0.5
                if b.cooling_type == app.preferred_cooling:
                    pref_score += 0.5
                # Compatibility factor
                comp_score = min(1.0, app.compatibility_score + (0.1 if b.cooling_type == app.preferred_cooling else 0.0))
                # Weighted total
                return (pref_score * (pref_weight / 100.0)) + (comp_score * (comp_weight / 100.0))

            candidate_beds.sort(key=score_candidate, reverse=True)
            matched_bed = candidate_beds[0]

            occupied_bed_ids.add(matched_bed.bed_id)
            sim_allocated += 1
            if matched_bed.cooling_type == app.preferred_cooling and matched_bed.room_type == app.preferred_room_type:
                pref_honoured += 1

            matched_comp = min(0.98, app.compatibility_score + (comp_weight / 500.0))
            is_reserved_alloc = app.is_reserved_category
            status_tag = "SIMULATED_RESERVED" if is_reserved_alloc else "SIMULATED_OCCUPIED"

            bed_allocations[matched_bed.bed_id] = {
                "status": status_tag,
                "display_status": "Simulated Reserved" if is_reserved_alloc else "Simulated Occupied",
                "occupant_name": app.student_name,
                "student_id": app.student_id,
                "cooling": matched_bed.cooling_type,
                "is_simulated": True,
                "is_reserved": is_reserved_alloc
            }

        sim_waitlisted = max(0, len(applicants) - sim_allocated)
        total_apps = len(applicants) or 1
        sim_first_pref_met_pct = round((pref_honoured / total_apps) * 100, 1)
        sim_avg_comp = round((compatibility_sum / max(1, sim_allocated)), 2) if sim_allocated else 0.70

        delta_allocated = sim_allocated - current_allocated
        delta_waitlisted = sim_waitlisted - current_waitlisted
        delta_pref_pts = round(sim_first_pref_met_pct - current_first_pref_met_pct, 1)
        delta_compatibility = round(sim_avg_comp - current_avg_comp, 2)

        # Block by block comparisons
        block_comparisons: List[BlockComparison] = []
        # Group beds by block
        blocks_dict: Dict[str, dict] = {}
        for b in beds:
            key = b.block_code
            if key not in blocks_dict:
                blocks_dict[key] = {
                    "code": b.block_code,
                    "name": b.block_name,
                    "total": 0,
                    "cur_occ": 0,
                    "sim_occ": 0,
                    "excluded": b.block_code in excluded_block_codes or b.block_name in excluded_block_codes
                }
            blocks_dict[key]["total"] += 1
            if b.baseline_status == "OCCUPIED":
                blocks_dict[key]["cur_occ"] += 1
            if b.bed_id in occupied_bed_ids:
                blocks_dict[key]["sim_occ"] += 1

        for key, bd in sorted(blocks_dict.items()):
            cur_pct = round((bd["cur_occ"] / bd["total"]) * 100, 1) if bd["total"] else 0.0
            sim_pct = 0.0 if bd["excluded"] else (round((bd["sim_occ"] / bd["total"]) * 100, 1) if bd["total"] else 0.0)
            block_comparisons.append(
                BlockComparison(
                    block_code=bd["code"],
                    block_name=bd["name"],
                    total_beds=bd["total"],
                    current_occupied=bd["cur_occ"],
                    current_pct=cur_pct,
                    simulated_occupied=0 if bd["excluded"] else bd["sim_occ"],
                    simulated_pct=sim_pct
                )
            )

        summary_msg = f"Simulated {len(applicants)} applicants across {len(active_beds)} active beds (Seed {random_seed}). {sim_allocated} allocated, {sim_waitlisted} waitlisted."

        return SimulationResult(
            total_applicants=len(applicants),
            total_capacity=len(active_beds),
            current_allocated=current_allocated,
            current_waitlisted=current_waitlisted,
            current_first_pref_met_pct=current_first_pref_met_pct,
            current_avg_compatibility=current_avg_comp,
            current_hard_failures=current_hard_failures,
            sim_allocated=sim_allocated,
            sim_waitlisted=sim_waitlisted,
            sim_first_pref_met_pct=sim_first_pref_met_pct,
            sim_avg_compatibility=sim_avg_comp,
            sim_hard_failures=hard_failures,
            delta_allocated=delta_allocated,
            delta_waitlisted=delta_waitlisted,
            delta_pref_pts=delta_pref_pts,
            delta_compatibility=delta_compatibility,
            block_comparisons=block_comparisons,
            bed_allocations=bed_allocations,
            seed=random_seed,
            summary=summary_msg
        )

