from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from planning_measurements.models import Goal, Period
from registration_validation.models import Activity, Evidence, Validation

from .models import Indicator
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
