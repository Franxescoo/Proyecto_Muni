from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from planning_measurements.models import Goal, Period
from registration_validation.models import Activity, Evidence, Validation

from .models import (
    Audit,
    Commitment,
    CommitmentComment,
    Indicator,
)
from .services import recalculate_indicator_for_goal


def _recalculate_goal(goal_id):
    if goal_id:
        goal = Goal.objects.filter(pk=goal_id).select_related(
            "employee", "period"
        ).first()
        if goal:
            recalculate_indicator_for_goal(
                goal,
                create_if_missing=False,
            )


@receiver([post_save, post_delete], sender=Evidence)
def evidence_changed(sender, instance, **kwargs):
    goal_id = instance.activity.goal_id if instance.activity_id else None
    if goal_id:
        goal = Goal.objects.filter(pk=goal_id).select_related(
            "employee", "period"
        ).first()
        if goal:
            recalculate_indicator_for_goal(goal, create_if_missing=True)


@receiver([post_save, post_delete], sender=Validation)
def validation_changed(sender, instance, **kwargs):
    evidence = instance.evidence
    goal_id = evidence.activity.goal_id if evidence.activity_id else None
    if goal_id:
        goal = Goal.objects.filter(pk=goal_id).select_related(
            "employee", "period"
        ).first()
        if goal:
            recalculate_indicator_for_goal(goal, create_if_missing=True)


@receiver([post_save, post_delete], sender=Activity)
def activity_changed(sender, instance, **kwargs):
    _recalculate_goal(instance.goal_id)


@receiver(post_save, sender=Goal)
def goal_changed(sender, instance, **kwargs):
    _recalculate_goal(instance.pk)


@receiver(post_save, sender=Period)
def period_changed(sender, instance, **kwargs):
    goal_ids = instance.goals.filter(
        deleted_at__isnull=True
    ).values_list("pk", flat=True)
    for goal_id in goal_ids:
        _recalculate_goal(goal_id)


@receiver(post_delete, sender=Period)
def period_deleted(sender, instance, **kwargs):
    Indicator.objects.filter(
        goal__period_id=instance.pk,
    ).update(
        actual_progress=0,
        difference=0,
        compliance=0,
        traffic_light="Red",
    )


def _audit_employee(instance):
    created_by = getattr(instance, "created_by", None)
    profile = getattr(created_by, "profile", None)
    if profile and profile.employee_id:
        return profile.employee

    for field_name in ("author", "verifier", "responsible", "employee"):
        employee = getattr(instance, field_name, None)
        if employee is not None:
            return employee

    if isinstance(instance, Commitment):
        return instance.responsible

    return None



def _record_audit(instance, event):
    employee = _audit_employee(instance)

    if employee is None:
        return

    previous_value = None
    new_value = None

    if isinstance(instance, Goal):
        campos = (
            "period_id",
            "employee_id",
            "position_id",
            "measurement_item_id",
            "item",
            "objective_value",
            "required_evidence_count",
            "unit",
            "weight",
        )

        previous_value = getattr(
            instance, "_audit_before", None
        )

        new_value = {
            "datos": {
                campo: str(getattr(instance, campo))
                for campo in campos
            },
            "editado_por": getattr(
                instance, "_audit_actor", None
            ),
        }

    elif isinstance(instance, CommitmentComment):
        new_value = {"text": instance.text}

    Audit.objects.create(
        user=employee,
        event=event,
        entity=instance.__class__.__name__,
        object_identifier=str(instance.pk),
        previous_value=previous_value,
        new_value=new_value,
    )



@receiver(post_save, sender=Commitment)
@receiver(post_save, sender=CommitmentComment)
@receiver(post_save, sender=Goal)
@receiver(post_save, sender=Activity)
@receiver(post_save, sender=Evidence)
@receiver(post_save, sender=Validation)
def tracked_object_saved(sender, instance, created, **kwargs):
    _record_audit(
        instance,
        f"{'Created' if created else 'Updated'} {sender.__name__}",
    )


@receiver(post_delete, sender=Commitment)
@receiver(post_delete, sender=CommitmentComment)
@receiver(post_delete, sender=Goal)
@receiver(post_delete, sender=Activity)
@receiver(post_delete, sender=Evidence)
@receiver(post_delete, sender=Validation)
def tracked_object_deleted(sender, instance, **kwargs):
    _record_audit(instance, f"Deleted {sender.__name__}")


# AUDITORÍA GENERAL DEL SGR

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import pre_save

from accounts.models import UserProfile
from organization.models import (
    Delegation,
    Employee,
    PositionFunction,
    OrganizationRole,
)
from planning_measurements.models import MeasurementItem
from registration_validation.models import (
    ActivityType,
    AttentionType,
    Service,
    SubAttention,
    AttentionEntry,
)
from .audit_context import get_audit_user


# Modelos que necesitan auditoría general.
# Los que ya tienen señales específicas quedan fuera.
GENERAL_AUDIT_MODELS = (
    get_user_model(),
    Group,
    UserProfile,
    Delegation,
    Employee,
    PositionFunction,
    OrganizationRole,
    Period,
    MeasurementItem,
    ActivityType,
    AttentionType,
    Service,
    SubAttention,
    AttentionEntry,
)

# No almacenar contraseñas ni determinados datos sensibles.
AUDIT_EXCLUDED_FIELDS = {
    "created_at",
    "updated_at",
    "password",
    "last_login",
    "email",
    "phone",
    "profile_photo",
    "employee_code",
}


def _general_audit_actor():
    user = get_audit_user()

    if user is None:
        return None

    profile = getattr(user, "profile", None)
    return getattr(profile, "employee", None)


def _general_audit_values(obj):
    values = {}

    for field in obj._meta.concrete_fields:
        if field.primary_key or field.name in AUDIT_EXCLUDED_FIELDS:
            continue

        value = getattr(obj, field.attname)
        values[field.attname] = (
            str(value) if value is not None else None
        )

    return values


@receiver(pre_save)
def general_audit_before(sender, instance, **kwargs):
    if sender not in GENERAL_AUDIT_MODELS:
        return

    if _general_audit_actor() is None:
        return

    previous = (
        sender.objects.filter(pk=instance.pk).first()
        if instance.pk else None
    )

    instance._general_audit_previous = (
        _general_audit_values(previous)
        if previous else None
    )


@receiver(post_save)
def general_audit_after(sender, instance, created, **kwargs):
    if sender not in GENERAL_AUDIT_MODELS:
        return

    employee = _general_audit_actor()
    if employee is None:
        return

    previous = getattr(
        instance, "_general_audit_previous", None
    )

    current = _general_audit_values(
        sender.objects.get(pk=instance.pk)
    )

    if created:
        before = None
        after = current
    else:
        if previous is None:
            return

        before = {
            key: value
            for key, value in previous.items()
            if value != current[key]
        }

        after = {
            key: current[key]
            for key in before
        }

        if not before:
            return

    # La reapertura ya tiene su propio registro con motivo.
    if (
        sender is Period
        and before == {"status": "Closed"}
        and after == {"status": "Active"}
    ):
        return

    Audit.objects.create(
        user=employee,
        event=(
            f"{'Created' if created else 'Updated'} "
            f"{sender.__name__}"
        ),
        entity=sender.__name__,
        object_identifier=str(instance.pk),
        previous_value=before,
        new_value={
            **after,
            "editado_por": get_audit_user().get_username(),
        },
    )


@receiver(post_delete)
def general_audit_deleted(sender, instance, **kwargs):
    if sender not in GENERAL_AUDIT_MODELS:
        return

    employee = _general_audit_actor()
    if employee is None:
        return

    Audit.objects.create(
        user=employee,
        event=f"Deleted {sender.__name__}",
        entity=sender.__name__,
        object_identifier=str(instance.pk),
        previous_value=_general_audit_values(instance),
        new_value={
            "editado_por": get_audit_user().get_username()
        },
    )
