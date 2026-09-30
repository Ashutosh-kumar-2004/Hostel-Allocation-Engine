import logging
from django.core.management import call_command

logger = logging.getLogger(__name__)

_AUTO_SEED_CHECKED = False

class AutoSeedMiddleware:
    """
    Middleware that checks if the database is seeded on the first incoming HTTP request.
    If unseeded (no Hostels or Allocation Cycles exist), it automatically runs 'seed_sample_data'.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        global _AUTO_SEED_CHECKED
        if not _AUTO_SEED_CHECKED:
            _AUTO_SEED_CHECKED = True
            try:
                from apps.inventory.models import Hostel
                from apps.applications.models import AllocationCycle
                if not Hostel.objects.exists() or not AllocationCycle.objects.exists():
                    logger.info("Unseeded database detected on request. Automatically executing seed_sample_data...")
                    call_command("seed_sample_data")
            except Exception as exc:
                # Silently log if migrations are not applied yet or during specific CLI runs
                logger.debug(f"Auto-seed check skipped: {exc}")

        return self.get_response(request)
