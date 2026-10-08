from .models import UserProfile


def sync_profile(profile):
    if not profile.employee_id:
        return

    delegation_id = profile.employee.delegation_id

    if profile.delegation_id != delegation_id:
        UserProfile.objects.filter(pk=profile.pk).update(
            delegation_id=delegation_id
        )


def sync_employee(employee):
    profiles = UserProfile.objects.filter(
        employee=employee
    ).select_related("employee")

    for profile in profiles:
        sync_profile(profile)


def sync_position(position):
    profiles = UserProfile.objects.filter(
        employee__position=position
    ).select_related("employee")

    for profile in profiles:
        sync_profile(profile)