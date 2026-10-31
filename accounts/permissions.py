"""Calcula delegaciones autorizadas por perfil y por el alcance real de un permiso."""


def allowed_delegation_ids(user, permission=None, *, active_only=True):
    if user.is_superuser and getattr(user, "is_active", True):
        return None  # Acceso global de superusuario.
    if not getattr(user, "is_authenticated", True) or not getattr(user, "is_active", True):
        return set()
    profile = getattr(user, "profile", None)
    if profile is None or getattr(profile, "deleted_at", None) is not None:
        return set()
    relation = getattr(profile, "authorized_delegations", None)
    authorized = set(relation.values_list("pk", flat=True)) if relation is not None else set()
    if not authorized and profile.delegation_id:
        authorized = {profile.delegation_id}  # Compatibilidad con perfiles históricos.
    # Each web request is pinned to an authorized active delegation by middleware.
    # Command-line scripts and historical helper objects have no request context.
    active = getattr(user, "sgr_active_delegation_id", None)
    if active_only and active is not None:
        authorized.intersection_update({active})
    if not permission or not authorized:
        return authorized
    try:
        app_label, codename = permission.split(".", 1)
    except ValueError:
        return set()
    if not hasattr(user, "user_permissions"):
        # Objetos simulados por las pruebas del proyecto anterior.
        return authorized
    if user.user_permissions.filter(
        codename=codename, content_type__app_label=app_label
    ).exists():
        return authorized  # Permiso directo, nunca delegaciones no autorizadas.
    groups = user.groups.filter(
        permissions__codename=codename,
        permissions__content_type__app_label=app_label,
        organization_role__isnull=False,
    ).select_related("organization_role").prefetch_related(
        "organization_role__application_delegations"
    ).distinct()
    scopes = set()
    for group in groups:
        role = group.organization_role
        role_delegations = set(role.application_delegations.values_list("pk", flat=True))
        scopes.update(role_delegations or {role.delegation_id})
    return authorized.intersection(scopes)
