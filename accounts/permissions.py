
"""Delegaciones autorizadas desde Funcionarios y permisos desde Usuarios."""

from organization.models import Delegation


def allowed_delegation_ids(user, permission=None, *, active_only=True):
    """
    Obtiene las delegaciones autorizadas para un usuario.

    Reglas:
    - Los roles determinan las operaciones permitidas.
    - Las delegaciones autorizadas provienen del perfil del funcionario.
    - No se utilizan las delegaciones de los roles como restricción adicional.
    - Se excluyen delegaciones inactivas y eliminadas lógicamente.
    - El selector global restringe la delegación activa cuando corresponde.
    """

    if (
        not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return set()

    # Compatibilidad con Django. La demostración utiliza usuarios normales.
    if getattr(user, "is_superuser", False):
        return None

    # El permiso determina QUÉ puede hacer el usuario.
    if permission and not user.has_perm(permission):
        return set()

    profile = getattr(user, "profile", None)

    if profile is None or profile.deleted_at is not None:
        return set()

    # Las delegaciones se administran desde Funcionarios.
    authorized = set(
        profile.authorized_delegations.values_list("pk", flat=True)
    )

    # Compatibilidad con perfiles antiguos.
    if not authorized and profile.delegation_id:
        authorized = {profile.delegation_id}  # Compatibilidad con perfiles históricos.

    # Evitar mostrar datos de delegaciones archivadas o inactivas.
    authorized = set(
        Delegation.objects.filter(
            pk__in=authorized,
            deleted_at__isnull=True,
            status__iexact="Active",
        ).values_list("pk", flat=True)
    )

    # El selector global restringe la delegación activa cuando corresponde.
    # Para operaciones sin solicitud web puede no existir selección activa.
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
        # Compatibilidad con objetos simulados en pruebas históricas.
        return authorized
    if user.user_permissions.filter(
        codename=codename, content_type__app_label=app_label
    ).exists():
        return authorized  # Permiso directo, nunca delegaciones no autorizadas.

    # El rol determina la operación; el perfil, las delegaciones autorizadas.
    # OrganizationRole.delegation y application_delegations no amplían el alcance.
    allowed_by_role = user.groups.filter(
        permissions__codename=codename,
        permissions__content_type__app_label=app_label,
        organization_role__isnull=False,
    ).exists()
    return authorized if allowed_by_role else set()
