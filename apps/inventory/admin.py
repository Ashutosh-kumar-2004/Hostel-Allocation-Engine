from django.contrib import admin
from .models import Hostel, Block, Room, Bed

@admin.register(Hostel)
class HostelAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "gender_type", "is_active", "institution_id")
    list_filter = ("gender_type", "is_active", "institution_id")
    search_fields = ("name", "code")

@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "hostel", "number_of_floors")
    list_filter = ("hostel",)

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("room_number", "block", "floor_number", "room_type", "capacity", "is_accessible", "is_active")
    list_filter = ("room_type", "is_accessible", "is_active", "block__hostel")
    search_fields = ("room_number",)

@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ("bed_identifier", "room", "status", "is_accessible")
    list_filter = ("status", "is_accessible", "room__block__hostel")
