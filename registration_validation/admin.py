from django.contrib import admin
from django.utils import timezone

from .models import Activity, Evidence, Validation


class DelegationForeignKeyMixin:
    """
    Restricts ForeignKey options according to the delegation
    assigned to the authenticated user's profile.
    """

    foreignkey_delegation_filters = {}

    def get_user_delegation_id(self, request):
        profile = getattr(request.user, "profile", None)

        if profile is None:
            return None

        return profile.delegation_id

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs,
    ):
        filter_path = self.foreignkey_delegation_filters.get(
            db_field.name
        )

        if (
            not request.user.is_superuser
            and filter_path is not None
        ):
            delegation_id = self.get_user_delegation_id(
                request
            )

            if delegation_id is None:
                kwargs["queryset"] = (
                    db_field.related_model.objects.none()
                )
            else:
                kwargs["queryset"] = (
                    db_field.related_model.objects.filter(
                        **{
                            filter_path: delegation_id,
                            "deleted_at__isnull": True,
                        }
                    )
                )

        return super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )


class DelegationRestrictedAdminMixin(
    DelegationForeignKeyMixin
):
    """
    Shared security rules for models restricted by delegation.
    """

    delegation_filter = None
    object_delegation_path = None

    readonly_fields = (
        "created_at",
        "updated_at",
        "deleted_at",
    )

    def get_nested_value(self, obj, path):
        value = obj

        for attribute in path.split("."):
            value = getattr(value, attribute)

        return value

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return request.user.is_superuser

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False

        if request.user.is_superuser:
            return True

        return (
            self.get_user_delegation_id(request)
            is not None
        )

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        if not super().has_change_permission(
            request,
            obj,
        ):
            return False

        if obj is None or request.user.is_superuser:
            return True

        delegation_id = self.get_user_delegation_id(
            request
        )

        if (
            delegation_id is None
            or self.object_delegation_path is None
        ):
            return False

        object_delegation_id = self.get_nested_value(
            obj,
            self.object_delegation_path,
        )

        return object_delegation_id == delegation_id

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .filter(deleted_at__isnull=True)
        )

        if request.user.is_superuser:
            return queryset

        delegation_id = self.get_user_delegation_id(
            request
        )

        if (
            delegation_id is None
            or self.delegation_filter is None
        ):
            return queryset.none()

        return queryset.filter(
            **{
                self.delegation_filter:
                    delegation_id
            }
        )


class EvidenceInline(
    DelegationForeignKeyMixin,
    admin.TabularInline,
):
    model = Evidence
    extra = 0

    fields = (
        "code",
        "author",
        "file_link",
        "date",
        "review_status",
    )

    foreignkey_delegation_filters = {
        "author": "delegation_id",
    }

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return request.user.is_superuser


@admin.register(Activity)
class ActivityAdmin(
    DelegationRestrictedAdminMixin,
    admin.ModelAdmin,
):
    delegation_filter = "author__delegation_id"

    object_delegation_path = (
        "author.delegation_id"
    )

    foreignkey_delegation_filters = {
        "author": "delegation_id",
        "goal": "employee__delegation_id",
    }

    list_display = (
        "activity_id",
        "goal",
        "author",
        "date",
        "status",
    )

    search_fields = (
        "request_problem",
        "action",
        "contact",
        "phone",
        "author__name",
        "goal__item",
    )

    list_filter = (
        "status",
        "date",
    )

    ordering = (
        "-date",
        "activity_id",
    )

    list_select_related = (
        "goal",
        "author",
    )

    date_hierarchy = "date"
    list_per_page = 25

    inlines = [
        EvidenceInline,
    ]


@admin.action(
    description="Archive selected evidence",
    permissions=["change"],
)
def archive_evidences(
    modeladmin,
    request,
    queryset,
):
    now = timezone.now()

    queryset.update(
        deleted_at=now,
        updated_at=now,
    )


@admin.register(Evidence)
class EvidenceAdmin(
    DelegationRestrictedAdminMixin,
    admin.ModelAdmin,
):
    delegation_filter = (
        "activity__author__delegation_id"
    )

    object_delegation_path = (
        "activity.author.delegation_id"
    )

    foreignkey_delegation_filters = {
        "author": "delegation_id",
        "activity": "author__delegation_id",
    }

    list_display = (
        "evidence_id",
        "code",
        "activity",
        "author",
        "date",
        "review_status",
    )

    search_fields = (
        "code",
        "activity__request_problem",
        "author__name",
    )

    list_filter = (
        "review_status",
        "date",
    )

    ordering = (
        "-date",
        "evidence_id",
    )

    list_select_related = (
        "activity",
        "author",
    )

    date_hierarchy = "date"
    list_per_page = 25

    actions = [
        archive_evidences,
    ]


@admin.register(Validation)
class ValidationAdmin(
    DelegationRestrictedAdminMixin,
    admin.ModelAdmin,
):
    delegation_filter = (
        "evidence__activity__author__delegation_id"
    )

    object_delegation_path = (
        "evidence.activity.author.delegation_id"
    )

    foreignkey_delegation_filters = {
        "verifier": "delegation_id",
        "evidence": (
            "activity__author__delegation_id"
        ),
    }

    list_display = (
        "validation_id",
        "evidence",
        "verifier",
        "decision",
        "date",
        "version",
    )

    search_fields = (
        "evidence__code",
        "verifier__name",
        "decision",
        "result",
        "observation",
    )

    list_filter = (
        "decision",
        "date",
    )

    ordering = (
        "-date",
        "-version",
    )

    list_select_related = (
        "evidence",
        "verifier",
    )

    date_hierarchy = "date"
    list_per_page = 25