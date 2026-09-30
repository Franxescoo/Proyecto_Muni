from django.contrib import admin
from django.utils import timezone

from .models import Activity, Evidence, Validation


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0

    fields = (
        "code",
        "author",
        "file_link",
        "date",
        "review_status",
    )

    autocomplete_fields = ("author",)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs,
    ):
        if (
            not request.user.is_superuser
            and db_field.name == "author"
        ):
            profile = getattr(
                request.user,
                "profile",
                None,
            )

            delegation_id = (
                profile.delegation_id
                if profile
                else None
            )

            if delegation_id is None:
                kwargs["queryset"] = (
                    db_field.related_model.objects.none()
                )
            else:
                kwargs["queryset"] = (
                    db_field.related_model.objects.filter(
                        delegation_id=delegation_id,
                        deleted_at__isnull=True,
                    )
                )

        return super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
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
    inlines = [EvidenceInline]

    readonly_fields = (
        "created_at",
        "updated_at",
        "deleted_at",
    )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .filter(deleted_at__isnull=True)
        )

        if request.user.is_superuser:
            return queryset

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        if (
            profile is None
            or profile.delegation_id is None
        ):
            return queryset.none()

        return queryset.filter(
            author__delegation_id=profile.delegation_id
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

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        return bool(
            profile
            and profile.delegation_id
            and obj.author.delegation_id
            == profile.delegation_id
        )

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False

        if request.user.is_superuser:
            return True

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        return bool(
            profile
            and profile.delegation_id
        )

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs,
    ):
        if not request.user.is_superuser:
            profile = getattr(
                request.user,
                "profile",
                None,
            )

            delegation_id = (
                profile.delegation_id
                if profile
                else None
            )

            if db_field.name == "author":
                if delegation_id is None:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.none()
                    )
                else:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.filter(
                            delegation_id=delegation_id,
                            deleted_at__isnull=True,
                        )
                    )

            elif db_field.name == "goal":
                if delegation_id is None:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.none()
                    )
                else:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.filter(
                            employee__delegation_id=delegation_id,
                            deleted_at__isnull=True,
                        )
                    )

        return super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )


@admin.action(
    description="Archive selected evidence",
    permissions=["change"],
)
def archive_evidences(modeladmin, request, queryset):
    now = timezone.now()

    queryset.update(
        deleted_at=now,
        updated_at=now,
    )


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
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

    readonly_fields = (
        "created_at",
        "updated_at",
        "deleted_at",
    )

    actions = [archive_evidences]

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .filter(deleted_at__isnull=True)
        )

        if request.user.is_superuser:
            return queryset

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        if (
            profile is None
            or profile.delegation_id is None
        ):
            return queryset.none()

        return queryset.filter(
            activity__author__delegation_id=
            profile.delegation_id
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

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        return bool(
            profile
            and profile.delegation_id
            and obj.activity.author.delegation_id
            == profile.delegation_id
        )

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False

        if request.user.is_superuser:
            return True

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        return bool(
            profile
            and profile.delegation_id
        )

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs,
    ):
        if not request.user.is_superuser:
            profile = getattr(
                request.user,
                "profile",
                None,
            )

            delegation_id = (
                profile.delegation_id
                if profile
                else None
            )

            if db_field.name == "author":
                if delegation_id is None:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.none()
                    )
                else:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.filter(
                            delegation_id=delegation_id,
                            deleted_at__isnull=True,
                        )
                    )

            elif db_field.name == "activity":
                if delegation_id is None:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.none()
                    )
                else:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.filter(
                            author__delegation_id=delegation_id,
                            deleted_at__isnull=True,
                        )
                    )

        return super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )


@admin.register(Validation)
class ValidationAdmin(admin.ModelAdmin):
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

    readonly_fields = (
        "created_at",
        "updated_at",
        "deleted_at",
    )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .filter(deleted_at__isnull=True)
        )

        if request.user.is_superuser:
            return queryset

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        if (
            profile is None
            or profile.delegation_id is None
        ):
            return queryset.none()

        return queryset.filter(
            evidence__activity__author__delegation_id=
            profile.delegation_id
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

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        return bool(
            profile
            and profile.delegation_id
            and obj.evidence.activity.author.delegation_id
            == profile.delegation_id
        )

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False

        if request.user.is_superuser:
            return True

        profile = getattr(
            request.user,
            "profile",
            None,
        )

        return bool(
            profile
            and profile.delegation_id
        )

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs,
    ):
        if not request.user.is_superuser:
            profile = getattr(
                request.user,
                "profile",
                None,
            )

            delegation_id = (
                profile.delegation_id
                if profile
                else None
            )

            if db_field.name == "verifier":
                if delegation_id is None:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.none()
                    )
                else:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.filter(
                            delegation_id=delegation_id,
                            deleted_at__isnull=True,
                        )
                    )

            elif db_field.name == "evidence":
                if delegation_id is None:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.none()
                    )
                else:
                    kwargs["queryset"] = (
                        db_field.related_model.objects.filter(
                            activity__author__delegation_id=
                            delegation_id,
                            deleted_at__isnull=True,
                        )
                    )

        return super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )