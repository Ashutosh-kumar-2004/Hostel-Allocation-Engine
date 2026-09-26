from typing import List
from .models import Application, AllocationCycle

class ApplicationService:
    @staticmethod
    def get_eligible_applications_for_cycle(cycle_id: str) -> List[Application]:
        return list(Application.objects.filter(
            cycle_id=cycle_id,
            status__in=["SUBMITTED", "ELIGIBLE"]
        ))
