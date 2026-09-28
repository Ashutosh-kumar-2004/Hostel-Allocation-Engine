from django.contrib import admin
from .models import AuditEntry

@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "target_entity", "target_id", "actor_email", "institution_id")
    list_filter = ("action", "target_entity", "institution_id")
    search_fields = ("actor_email", "target_id", "reason")
    readonly_fields = [f.name for f in AuditEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
