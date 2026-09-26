from django.contrib import admin
from .models import AllocationCycle, Application

@admin.register(AllocationCycle)
class AllocationCycleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "academic_year", "status", "application_start", "application_end")
    list_filter = ("status", "academic_year")
    search_fields = ("name", "code")

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("student_name", "student_id", "cycle", "gender", "programme", "status", "requires_accessible_room")
    list_filter = ("status", "gender", "cycle", "requires_accessible_room")
    search_fields = ("student_name", "student_id", "student_email")
