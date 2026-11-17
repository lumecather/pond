from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class PondUserAdmin(UserAdmin):
    list_display = ("username", "live_enabled", "pro_mode", "last_login")
    fieldsets = UserAdmin.fieldsets + (("Trading", {"fields": ("pro_mode", "live_enabled", "slippage_bps")}),)
