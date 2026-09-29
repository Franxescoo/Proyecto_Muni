from django.contrib import admin, messages
from django.utils import timezone

from .models import Period, Goal


@admin.action(
    description="Delete", permissions=["change"]
)
def archive_records(modeladmin, request, queryset):
    updated = queryset.filter(deleted_at__isnull=True).update(
        deleted_at=timezone.now()
    )
    modeladmin.message_user(
        request,
        f"{updated} Deleted successfully.",
        level=messages.SUCCESS,
    )


class GoalInline(admin.TabularInline):
    model = Goal
    extra = 0
    fields = ("employee", "position", "item", "objective_value", "unit", "weight")
    show_change_link = True


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = (
        "period_id",
        "start_date",
        "end_date",
        "computable_days",
        "status",
        "parameters_version",
    )
    search_fields = ("status", "parameters_version")
    list_filter = ("status",)
    ordering = ("-start_date",)
    inlines = [GoalInline]
    actions = [archive_records]

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(deleted_at__isnull=True)


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = (
        "goal_id",
        "item",
        "period",
        "employee",
        "position",
        "objective_value",
        "unit",
        "weight",
    )
    list_select_related = ("period", "employee", "position")
    search_fields = ("item", "employee__name")
    list_filter = ("period", "position", "unit")
    ordering = ("period", "item")
    actions = [archive_records]

    def has_delete_permission(self, request, obj=None):
        return False

    def _user_delegation_id(self, request):
        profile = getattr(request.user, "profile", None)
        return profile.delegation_id if profile else None

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(deleted_at__isnull=True)
        if request.user.is_superuser:
            return qs
        delegation_id = self._user_delegation_id(request)
        if delegation_id is None:
            return qs.none()
        return qs.filter(employee__delegation_id=delegation_id)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "employee":
            queryset = db_field.related_model.objects.filter(
                deleted_at__isnull=True
            )
            if not request.user.is_superuser:
                queryset = queryset.filter(
                    delegation_id=self._user_delegation_id(request)
                )
            kwargs["queryset"] = queryset
        return super().formfield_for_foreignkey(db_field, request, **kwargs)