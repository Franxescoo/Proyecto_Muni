"""Read-only inventory of direct user permissions."""


def direct_permission_inventory(user_model):
    """Return direct permissions and role coverage without exposing secrets."""
    inventory = []
    users = user_model.objects.filter(
        is_superuser=False,
    ).prefetch_related(
        "groups__permissions__content_type",
        "user_permissions__content_type",
    ).order_by("username")

    for user in users:
        roles = list(user.groups.all())
        role_permissions = {
            f"{permission.content_type.app_label}.{permission.codename}"
            for role in roles
            for permission in role.permissions.all()
        }
        role_names = [role.name for role in roles]
        direct_permissions = sorted(
            (
                f"{permission.content_type.app_label}.{permission.codename}"
                for permission in user.user_permissions.all()
            ),
        )
        for permission_name in direct_permissions:
            inventory.append(
                {
                    "username": user.username,
                    "direct_permission": permission_name,
                    "roles": role_names,
                    "covered_by_role": permission_name in role_permissions,
                }
            )
    return inventory
