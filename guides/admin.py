from django.contrib import admin

from .models import Guide


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = ("title", "level", "order", "minutes", "is_published")
    list_editable = ("order", "is_published")
    list_filter = ("level", "is_published")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "body")
