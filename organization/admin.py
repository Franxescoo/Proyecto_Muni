from django.contrib import admin

from .models import Delegation, PositionFunction, Employee


class EmployeeInline(admin.TabularInline):
    model = Employee
    extra = 0


@admin.register(Delegation)
class DelegationAdmin(admin.ModelAdmin):
    list_display = (
        "delegation_id",
        "name",
        "status",
        "scope",
    )
    inlines = [EmployeeInline]


@admin.register(PositionFunction)
class PositionFunctionAdmin(admin.ModelAdmin):
    list_display = (
        "position_id",
        "position_name",
        "validity_start",
        "validity_end",
    )


@admin.action(description="Mark employees as inactive")
def mark_inactive(modeladmin, request, queryset):
    queryset.update(status="Inactive")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_id",
        "name",
        "delegation",
        "position",
        "status",
    )

    search_fields = ("name",)

    list_filter = (
        "status",
        "delegation",
        "position",
    )

    actions = [mark_inactive]

    def get_actions(self, request):
        actions = super().get_actions(request)

        if not request.user.has_perm("organization.change_employee"):
            actions.pop("mark_inactive", None)

        return actions