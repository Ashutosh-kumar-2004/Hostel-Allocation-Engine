from django.apps import AppConfig
from django.db.models.signals import post_migrate

def auto_seed_on_post_migrate(sender, **kwargs):
    """Automatically seed default data if database has no hostels/cycles after migrations."""
    if sender.name == "apps.core":
        try:
            from apps.inventory.models import Hostel
            from apps.applications.models import AllocationCycle
            if not Hostel.objects.exists() or not AllocationCycle.objects.exists():
                from django.core.management import call_command
                call_command("seed_sample_data")
        except Exception:
            pass

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'

    def ready(self):
        post_migrate.connect(auto_seed_on_post_migrate, sender=self)
