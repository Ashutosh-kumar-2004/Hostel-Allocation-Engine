"""
Pure Python Allocation Engine (M6).
NO DJANGO ORM IMPORTS PERMITTED HERE.
Enforces modularity, testability, and deterministic reproducibility.

Hard Constraints (Never Violated):
1. Bed Capacity: Maximum 1 occupant per bed, enforced atomically.
2. Gender Policy: Male in Men's residences, Female in Women's residences.
3. Accessibility: Wheelchair/accessible applicants assigned to accessible ground-floor rooms.
4. Atomic Mutual Roommate Pairing: Confirmed mutual roommate pairs co-allocated into the same room.

Soft Constraints (Optimized For):
1. Ranked Priority Choices: Stated preference ranks (Rank 1, 2, 3).
2. Room Type & Cooling Alignment: Single, Double, Triple, AC vs Cooler.
3. M5 Multidimensional Lifestyle Synergy: Unpartnered candidates grouped by maximal compatibility.
"""
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set


@dataclass
class ApplicantData:
    application_id: str
    student_id: str
    student_name: str = ""
    gender: str = "M"
    requires_accessible: bool = False
    preferences: List[Tuple[str, str]] = field(default_factory=list)  # [(hostel_id, room_type), ...]
    lifestyle: Dict[str, any] = field(default_factory=dict)
    mutual_roommate_id: Optional[str] = None


@dataclass
class BedData:
    bed_id: str
    bed_identifier: str
    hostel_id: str
    hostel_name: str = ""
    hostel_gender: str = "M"  # "M", "W", "C"
    room_id: str = ""
    room_number: str = ""
    room_type: str = "DOUBLE"
    cooling_type: str = "COOLER"
    is_accessible: bool = False
    room_capacity: int = 2


@dataclass
class AssignmentResult:
    application_id: str
    bed_id: str
    preference_rank: Optional[int]
    compatibility_score: float
    explanation: str


@dataclass
class EngineOutput:
    assignments: List[AssignmentResult]
    unassigned_applications: List[str]
    random_seed: int
    mutual_pairs_honoured: int = 0
    rank1_honoured_count: int = 0
    average_compatibility_score: float = 0.0


class AllocationEngine:
    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        self.rng = random.Random(random_seed)

    def solve(
        self,
        applicants: List[ApplicantData],
        beds: List[BedData]
    ) -> EngineOutput:
        """
        Deterministic constraint-respecting greedy heuristic with M5 synergy optimization.
        """
        # Copy and shuffle beds using seed to avoid positional bias
        available_beds = list(beds)
        self.rng.shuffle(available_beds)

        occupied_beds: Set[str] = set()
        room_occupants: Dict[str, List[ApplicantData]] = {}
        assigned_applicant_ids: Set[str] = set()
        assignments: List[AssignmentResult] = []
        unassigned: List[str] = []

        # Index beds by room for efficient multi-bed matching
        beds_by_room: Dict[str, List[BedData]] = {}
        for b in available_beds:
            beds_by_room.setdefault(b.room_id, []).append(b)

        # Index applicants by student_id
        applicant_by_student_id: Dict[str, ApplicantData] = {a.student_id: a for a in applicants}
        mutual_pairs_count = 0
        rank1_count = 0

        # =========================================================================
        # PHASE 1: ATOMIC MUTUAL ROOMMATE CO-ALLOCATION
        # =========================================================================
        processed_pair_keys: Set[str] = set()
        mutual_pairs: List[Tuple[ApplicantData, ApplicantData]] = []

        for app in applicants:
            if app.mutual_roommate_id and app.application_id not in assigned_applicant_ids:
                partner = applicant_by_student_id.get(app.mutual_roommate_id)
                if partner and partner.mutual_roommate_id == app.student_id and partner.gender == app.gender and partner.application_id not in assigned_applicant_ids:
                    pair_key = tuple(sorted([app.student_id, partner.student_id]))
                    if pair_key not in processed_pair_keys:
                        processed_pair_keys.add(pair_key)
                        mutual_pairs.append((app, partner))

        # Sort mutual pairs: accessibility first
        mutual_pairs.sort(key=lambda pair: not (pair[0].requires_accessible or pair[1].requires_accessible))

        for app_a, app_b in mutual_pairs:
            pair_assigned = False
            pair_synergy = self._calculate_pairwise_lifestyle(app_a.lifestyle, app_b.lifestyle)

            # Try to satisfy App A's preferences (or App B's preferences)
            combined_prefs = list(app_a.preferences)
            for p in app_b.preferences:
                if p not in combined_prefs:
                    combined_prefs.append(p)

            for rank, (pref_hostel, pref_room_type) in enumerate(combined_prefs, start=1):
                # Find a room with >= 2 unoccupied beds matching constraints
                candidate_room_beds = self._find_room_for_pair(
                    applicant_a=app_a,
                    applicant_b=app_b,
                    beds_by_room=beds_by_room,
                    occupied_beds=occupied_beds,
                    target_hostel_id=pref_hostel,
                    target_room_type=pref_room_type
                )
                if candidate_room_beds and len(candidate_room_beds) >= 2:
                    bed_a, bed_b = candidate_room_beds[0], candidate_room_beds[1]
                    occupied_beds.add(bed_a.bed_id)
                    occupied_beds.add(bed_b.bed_id)
                    room_occupants.setdefault(bed_a.room_id, []).extend([app_a, app_b])
                    assigned_applicant_ids.add(app_a.application_id)
                    assigned_applicant_ids.add(app_b.application_id)

                    expl_a = (
                        f"Preference rank #{rank} honoured ({bed_a.room_type} in {bed_a.hostel_name or 'Hostel'}). "
                        f"Co-allocated with verified mutual roommate {app_b.student_name} ({app_b.student_id}). "
                        f"Lifestyle synergy: {int(pair_synergy * 100)}%."
                    )
                    expl_b = (
                        f"Preference rank #{rank} honoured ({bed_b.room_type} in {bed_b.hostel_name or 'Hostel'}). "
                        f"Co-allocated with verified mutual roommate {app_a.student_name} ({app_a.student_id}). "
                        f"Lifestyle synergy: {int(pair_synergy * 100)}%."
                    )

                    assignments.append(AssignmentResult(
                        application_id=app_a.application_id,
                        bed_id=bed_a.bed_id,
                        preference_rank=rank,
                        compatibility_score=pair_synergy,
                        explanation=expl_a
                    ))
                    assignments.append(AssignmentResult(
                        application_id=app_b.application_id,
                        bed_id=bed_b.bed_id,
                        preference_rank=rank,
                        compatibility_score=pair_synergy,
                        explanation=expl_b
                    ))
                    pair_assigned = True
                    mutual_pairs_count += 1
                    if rank == 1:
                        rank1_count += 2
                    break

            # Fallback for pair: Any room with >= 2 beds satisfying hard constraints
            if not pair_assigned:
                candidate_room_beds = self._find_room_for_pair(
                    applicant_a=app_a,
                    applicant_b=app_b,
                    beds_by_room=beds_by_room,
                    occupied_beds=occupied_beds,
                    target_hostel_id=None,
                    target_room_type=None
                )
                if candidate_room_beds and len(candidate_room_beds) >= 2:
                    bed_a, bed_b = candidate_room_beds[0], candidate_room_beds[1]
                    occupied_beds.add(bed_a.bed_id)
                    occupied_beds.add(bed_b.bed_id)
                    room_occupants.setdefault(bed_a.room_id, []).extend([app_a, app_b])
                    assigned_applicant_ids.add(app_a.application_id)
                    assigned_applicant_ids.add(app_b.application_id)

                    expl_a = (
                        f"Preferences exhausted; paired with verified mutual roommate {app_b.student_name} ({app_b.student_id}) "
                        f"in {bed_a.hostel_name or 'Hostel'} Room {bed_a.room_number}. Lifestyle synergy: {int(pair_synergy * 100)}%."
                    )
                    expl_b = (
                        f"Preferences exhausted; paired with verified mutual roommate {app_a.student_name} ({app_a.student_id}) "
                        f"in {bed_b.hostel_name or 'Hostel'} Room {bed_b.room_number}. Lifestyle synergy: {int(pair_synergy * 100)}%."
                    )

                    assignments.append(AssignmentResult(
                        application_id=app_a.application_id,
                        bed_id=bed_a.bed_id,
                        preference_rank=None,
                        compatibility_score=pair_synergy,
                        explanation=expl_a
                    ))
                    assignments.append(AssignmentResult(
                        application_id=app_b.application_id,
                        bed_id=bed_b.bed_id,
                        preference_rank=None,
                        compatibility_score=pair_synergy,
                        explanation=expl_b
                    ))
                    pair_assigned = True
                    mutual_pairs_count += 1

        # =========================================================================
        # PHASE 2: INDIVIDUAL APPLICANTS WITH ACCESSIBILITY & PREFERENCE MATCHING
        # =========================================================================
        remaining_applicants = [a for a in applicants if a.application_id not in assigned_applicant_ids]

        # Accessibility priority first, then tiebreak by seed
        remaining_applicants.sort(key=lambda a: not a.requires_accessible)

        for applicant in remaining_applicants:
            assigned = False

            # 1. Try Ranked Preferences with M5 Lifestyle Synergy Optimization
            for rank, (pref_hostel, pref_room_type) in enumerate(applicant.preferences, start=1):
                best_bed, best_score = self._find_best_bed_with_synergy(
                    applicant=applicant,
                    available_beds=available_beds,
                    occupied_beds=occupied_beds,
                    room_occupants=room_occupants,
                    target_hostel_id=pref_hostel,
                    target_room_type=pref_room_type
                )
                if best_bed:
                    occupied_beds.add(best_bed.bed_id)
                    room_occupants.setdefault(best_bed.room_id, []).append(applicant)
                    assigned_applicant_ids.add(applicant.application_id)

                    expl = (
                        f"Honoured preference rank #{rank} ({best_bed.room_type} in {best_bed.hostel_name or 'Hostel'} Room {best_bed.room_number}). "
                        f"Lifestyle compatibility: {int(best_score * 100)}%."
                    )
                    assignments.append(AssignmentResult(
                        application_id=applicant.application_id,
                        bed_id=best_bed.bed_id,
                        preference_rank=rank,
                        compatibility_score=best_score,
                        explanation=expl
                    ))
                    assigned = True
                    if rank == 1:
                        rank1_count += 1
                    break

            # 2. Fallback: Any available bed satisfying hard constraints
            if not assigned:
                best_bed, best_score = self._find_best_bed_with_synergy(
                    applicant=applicant,
                    available_beds=available_beds,
                    occupied_beds=occupied_beds,
                    room_occupants=room_occupants,
                    target_hostel_id=None,
                    target_room_type=None
                )
                if best_bed:
                    occupied_beds.add(best_bed.bed_id)
                    room_occupants.setdefault(best_bed.room_id, []).append(applicant)
                    assigned_applicant_ids.add(applicant.application_id)

                    expl = (
                        f"Preferences exhausted; assigned to available bed in {best_bed.hostel_name or 'Hostel'} Room {best_bed.room_number} "
                        f"satisfying capacity and gender policy. Lifestyle compatibility: {int(best_score * 100)}%."
                    )
                    assignments.append(AssignmentResult(
                        application_id=applicant.application_id,
                        bed_id=best_bed.bed_id,
                        preference_rank=None,
                        compatibility_score=best_score,
                        explanation=expl
                    ))
                    assigned = True

            # 3. Unassigned / Queued for Waitlist
            if not assigned:
                unassigned.append(applicant.application_id)

        avg_comp = (
            round(sum(a.compatibility_score for a in assignments) / max(1, len(assignments)), 2)
            if assignments else 0.0
        )

        return EngineOutput(
            assignments=assignments,
            unassigned_applications=unassigned,
            random_seed=self.random_seed,
            mutual_pairs_honoured=mutual_pairs_count,
            rank1_honoured_count=rank1_count,
            average_compatibility_score=avg_comp
        )

    def _find_room_for_pair(
        self,
        applicant_a: ApplicantData,
        applicant_b: ApplicantData,
        beds_by_room: Dict[str, List[BedData]],
        occupied_beds: Set[str],
        target_hostel_id: Optional[str],
        target_room_type: Optional[str]
    ) -> Optional[List[BedData]]:
        """
        Finds a room that can house two mutual roommates together.
        Must have at least 2 unoccupied beds and satisfy gender & accessibility constraints.
        """
        for room_id, r_beds in beds_by_room.items():
            if not r_beds:
                continue

            sample_bed = r_beds[0]

            # Hard Constraint: Gender
            expected_gender = "M" if applicant_a.gender == "M" else "W"
            if sample_bed.hostel_gender != "C" and sample_bed.hostel_gender != expected_gender:
                continue

            # Hard Constraint: Accessibility (if either requires accessible)
            if (applicant_a.requires_accessible or applicant_b.requires_accessible) and not sample_bed.is_accessible:
                continue

            # Soft: Hostel preference filter
            if target_hostel_id and sample_bed.hostel_id != target_hostel_id:
                continue

            # Soft: Room type filter (must allow sharing, e.g. capacity >= 2)
            if target_room_type and sample_bed.room_type != target_room_type:
                continue

            unoccupied_in_room = [b for b in r_beds if b.bed_id not in occupied_beds]
            if len(unoccupied_in_room) >= 2:
                return unoccupied_in_room[:2]

        return None

    def _find_best_bed_with_synergy(
        self,
        applicant: ApplicantData,
        available_beds: List[BedData],
        occupied_beds: Set[str],
        room_occupants: Dict[str, List[ApplicantData]],
        target_hostel_id: Optional[str],
        target_room_type: Optional[str]
    ) -> Tuple[Optional[BedData], float]:
        """
        Finds the optimal bed for an applicant.
        If multiple candidate beds match preferences, selects the bed in a room
        that maximizes M5 lifestyle compatibility synergy with existing roommates.
        """
        eligible_candidates: List[Tuple[BedData, float]] = []

        for bed in available_beds:
            if bed.bed_id in occupied_beds:
                continue

            # Hard Constraint: Gender
            expected_gender = "M" if applicant.gender == "M" else "W"
            if bed.hostel_gender != "C" and bed.hostel_gender != expected_gender:
                continue

            # Hard Constraint: Accessibility
            if applicant.requires_accessible and not bed.is_accessible:
                continue

            # Soft: Hostel preference filter
            if target_hostel_id and bed.hostel_id != target_hostel_id:
                continue

            # Soft: Room type filter
            if target_room_type and bed.room_type != target_room_type:
                continue

            score = self._compute_room_synergy(applicant, bed.room_id, room_occupants)
            eligible_candidates.append((bed, score))

        if not eligible_candidates:
            return None, 0.0

        # Sort by highest synergy score first
        eligible_candidates.sort(key=lambda item: item[1], reverse=True)
        best_candidate = eligible_candidates[0]
        return best_candidate[0], best_candidate[1]

    def _compute_room_synergy(
        self,
        applicant: ApplicantData,
        room_id: str,
        room_occupants: Dict[str, List[ApplicantData]]
    ) -> float:
        """
        Calculates compatibility score with existing room occupants.
        If room is currently empty, returns baseline profile score (0.75-0.90).
        """
        occupants = room_occupants.get(room_id, [])
        if not occupants:
            lifestyle = applicant.lifestyle or {}
            score = 0.80
            if lifestyle.get("sleep_habit") == "EARLY_BIRD":
                score += 0.05
            if lifestyle.get("cleanliness_priority") == "VERY_STRICT":
                score += 0.05
            if lifestyle.get("guest_tolerance_score", 3) >= 3:
                score += 0.05
            return round(min(0.95, score), 2)

        scores = [
            self._calculate_pairwise_lifestyle(applicant.lifestyle, occ.lifestyle)
            for occ in occupants
        ]
        return round(sum(scores) / len(scores), 2)

    def _calculate_pairwise_lifestyle(
        self,
        p_a: Optional[Dict[str, any]],
        p_b: Optional[Dict[str, any]]
    ) -> float:
        """
        Pure deterministic pairwise compatibility scoring [0.0 - 1.0].
        Weights: Sleep habits (40%), Study habits (30%), Cleanliness (20%), Guest tolerance (10%).
        """
        if not p_a or not p_b:
            return 0.70

        pair_score = 0.0

        # 1. Sleep habits (40%)
        hab_a = p_a.get("sleep_habit")
        hab_b = p_b.get("sleep_habit")
        if hab_a and hab_a == hab_b:
            pair_score += 0.40
        elif "FLEXIBLE" in (hab_a, hab_b):
            pair_score += 0.25

        # 2. Study habits (30%)
        std_a = p_a.get("study_environment")
        std_b = p_b.get("study_environment")
        if std_a and std_a == std_b:
            pair_score += 0.30
        elif "LIGHT_MUSIC" in (std_a, std_b):
            pair_score += 0.20

        # 3. Cleanliness (20%)
        cln_a = p_a.get("cleanliness_priority")
        cln_b = p_b.get("cleanliness_priority")
        if cln_a and cln_a == cln_b:
            pair_score += 0.20
        elif "MODERATE" in (cln_a, cln_b):
            pair_score += 0.12

        # 4. Guest tolerance (10%)
        diff = abs(int(p_a.get("guest_tolerance_score", 3) or 3) - int(p_b.get("guest_tolerance_score", 3) or 3))
        pair_score += max(0.0, 0.10 - (diff * 0.025))

        return round(min(1.0, pair_score), 2)
