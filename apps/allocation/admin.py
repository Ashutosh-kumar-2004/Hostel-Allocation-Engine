from django.contrib import admin
from .models import AllocationDraft, AllocationAssignment

@admin.register(AllocationDraft)
class AllocationDraftAdmin(admin.ModelAdmin):
    list_display = ("run_identifier", "cycle", "status", "assigned_count", "total_applicants", "random_seed", "created_at")
    list_filter = ("status", "cycle")
    search_fields = ("run_identifier",)

@admin.register(AllocationAssignment)
class AllocationAssignmentAdmin(admin.ModelAdmin):
    list_display = ("application", "bed", "draft", "preference_rank_honoured", "compatibility_score")
    list_filter = ("draft", "preference_rank_honoured")
    search_fields = ("application__student_name", "application__student_id")
