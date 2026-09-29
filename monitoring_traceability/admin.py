from django.contrib import admin

from .models import Activity, Audit, Commitment, Evidence, Indicator


class CommitmentInline(admin.TabularInline):
	model = Commitment
	extra = 0
	fields = (
		"delegation",
		"responsible",
		"requester",
		"territory",
		"commitment_date",
		"status",
	)
	show_change_link = True


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
	list_display = ("activity_id", "name", "created_at", "updated_at")
	search_fields = ("name",)
	ordering = ("name",)
	inlines = [CommitmentInline]

	def get_queryset(self, request):
		return super().get_queryset(request).filter(deleted_at__isnull=True)

	def has_delete_permission(self, request, obj=None):
		return request.user.is_superuser


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
	list_display = ("evidence_id", "name", "created_at", "updated_at")
	search_fields = ("name",)
	ordering = ("name",)

	def get_queryset(self, request):
		return super().get_queryset(request).filter(deleted_at__isnull=True)

	def has_delete_permission(self, request, obj=None):
		return request.user.is_superuser


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
	list_display = (
		"indicator_id",
		"goal",
		"employee",
		"actual_progress",
		"compliance",
		"weighting",
		"traffic_light",
		"calculation_date",
	)
	list_select_related = ("goal", "employee", "goal__period")
	search_fields = ("goal__item", "employee__name", "traffic_light")
	list_filter = ("traffic_light", "calculation_date", "goal__period")
	ordering = ("-calculation_date", "indicator_id")

	def has_delete_permission(self, request, obj=None):
		return request.user.is_superuser

	def get_queryset(self, request):
		queryset = super().get_queryset(request).filter(deleted_at__isnull=True)
		if request.user.is_superuser:
			return queryset
		profile = getattr(request.user, "profile", None)
		if profile is None or profile.delegation_id is None:
			return queryset.none()
		return queryset.filter(employee__delegation_id=profile.delegation_id)

	def has_change_permission(self, request, obj=None):
		if not super().has_change_permission(request, obj):
			return False
		if obj is None or request.user.is_superuser:
			return True
		profile = getattr(request.user, "profile", None)
		return bool(
			profile
			and profile.delegation_id
			and obj.employee.delegation_id == profile.delegation_id
		)

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if not request.user.is_superuser and db_field.name in {"employee", "goal"}:
			profile = getattr(request.user, "profile", None)
			delegation_id = profile.delegation_id if profile else None
			if db_field.name == "employee":
				kwargs["queryset"] = db_field.related_model.objects.filter(
					delegation_id=delegation_id,
					deleted_at__isnull=True,
				)
			else:
				kwargs["queryset"] = db_field.related_model.objects.filter(
					employee__delegation_id=delegation_id,
					deleted_at__isnull=True,
				)
		return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Commitment)
class CommitmentAdmin(admin.ModelAdmin):
	list_display = (
		"commitment_id",
		"delegation",
		"responsible",
		"requester",
		"territory",
		"commitment_date",
		"status",
	)
	list_select_related = ("delegation", "responsible", "activity", "evidence")
	search_fields = ("requester", "territory", "observation", "responsible__name")
	list_filter = ("delegation", "status", "commitment_date")
	ordering = ("-commitment_date", "commitment_id")

	def has_delete_permission(self, request, obj=None):
		return request.user.is_superuser

	def get_queryset(self, request):
		queryset = super().get_queryset(request).filter(deleted_at__isnull=True)
		if request.user.is_superuser:
			return queryset
		profile = getattr(request.user, "profile", None)
		if profile is None or profile.delegation_id is None:
			return queryset.none()
		return queryset.filter(delegation_id=profile.delegation_id)

	def has_change_permission(self, request, obj=None):
		if not super().has_change_permission(request, obj):
			return False
		if obj is None or request.user.is_superuser:
			return True
		profile = getattr(request.user, "profile", None)
		return bool(
			profile
			and profile.delegation_id == obj.delegation_id
		)

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if not request.user.is_superuser and db_field.name in {"delegation", "responsible"}:
			profile = getattr(request.user, "profile", None)
			delegation_id = profile.delegation_id if profile else None
			kwargs["queryset"] = db_field.related_model.objects.filter(
				delegation_id=delegation_id,
				deleted_at__isnull=True,
			)
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

	def save_model(self, request, obj, form, change):
		if not request.user.is_superuser:
			profile = getattr(request.user, "profile", None)
			if profile is not None:
				obj.delegation_id = profile.delegation_id
		super().save_model(request, obj, form, change)


@admin.register(Audit)
class AuditAdmin(admin.ModelAdmin):
	list_display = (
		"audit_id",
		"event",
		"event_date",
		"entity",
		"object_identifier",
		"user",
	)
	list_select_related = ("user",)
	search_fields = ("event", "entity", "object_identifier", "user__name")
	list_filter = ("event", "entity", "event_date")
	ordering = ("-event_date", "-audit_id")

	def has_add_permission(self, request):
		return request.user.is_superuser

	def has_change_permission(self, request, obj=None):
		return request.user.is_superuser

	def has_delete_permission(self, request, obj=None):
		return request.user.is_superuser

	def get_queryset(self, request):
		queryset = super().get_queryset(request)
		if request.user.is_superuser:
			return queryset
		profile = getattr(request.user, "profile", None)
		if profile is None or profile.delegation_id is None:
			return queryset.none()
		return queryset.filter(user__delegation_id=profile.delegation_id)
from django.contrib import admin

# Register your models here.
