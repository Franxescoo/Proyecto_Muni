"""Read-only comparison for the legacy role territorial scopes."""

from accounts.permissions import allowed_delegation_ids


def delegation_transition_inventory(user_model):
    """Compare current permission scopes with the user-only proposal."""
    inventory = []
    users = user_model.objects.filter(
        is_active=True,
        is_superuser=False,
        profile__deleted_at__isnull=True,
    ).prefetch_related(
        "groups__permissions__content_type",
        "profile__authorized_delegations",
    ).order_by("username")

    for user in users:
        profile = user.profile
        authorized = set(
            profile.authorized_delegations.values_list("pk", flat=True)
        )
        if not authorized and profile.delegation_id:
            authorized = {profile.delegation_id}

        permissions = sorted(user.get_all_permissions())
        for permission in permissions:
            current = set(
                allowed_delegation_ids(
                    user,
                    permission,
                    active_only=False,
                )
                or ()
            )
            proposed = authorized
            if current != proposed:
                role_scopes = []
                for group in user.groups.all():
                    role_permissions = {
                        f"{item.content_type.app_label}.{item.codename}"
                        for item in group.permissions.all()
                    }
                    if permission in role_permissions:
                        role = getattr(group, "organization_role", None)
                        if role is not None:
                            scope = set(
                                role.application_delegations.values_list(
                                    "pk",
                                    flat=True,
                                )
                            ) or {role.delegation_id}
                            role_scopes.append(
                                {
                                    "role": group.name,
                                    "delegations": sorted(scope),
                                }
                            )
                inventory.append(
                    {
                        "username": user.username,
                        "permission": permission,
                        "authorized_delegations": sorted(authorized),
                        "current_delegations": sorted(current),
                        "proposed_delegations": sorted(proposed),
                        "would_gain": sorted(proposed - current),
                        "would_lose": sorted(current - proposed),
                        "role_scopes": role_scopes,
                    }
                )
    return inventory
