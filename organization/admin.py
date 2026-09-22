from django.contrib import admin

# Register your models here.
#jajkaasjd 
from .models import Organization



@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "tax_id",
        "is_active",
        "created_at",
    )
    search_fields = ("name", "tax_id")
    list_filter = ("is_active",)
    ordering = ("name",)
    list_per_page = 25

