"""Reglas reutilizables para permisos y alcance territorial."""

from .models import RoleScope


def is_general_administrator(user):
    """Indica si el usuario puede administrar todo el sistema.

    ``is_superuser`` se mantiene temporalmente para no bloquear al
    administrador actual mientras se asigna el rol Administrador General.
    """

    if not user.is_authenticated:
        return False

    return user.is_superuser or RoleScope.objects.filter(
        group__user=user,
        all_delegations=True,
    ).exists()


def allowed_delegation_ids(user):
    """Obtiene las delegaciones visibles por un usuario no global.

    La delegación asociada a su funcionario es el límite por defecto. Si
    el rol tiene delegaciones configuradas, estas solo pueden restringir
    ese alcance, nunca ampliarlo.
    """

    if is_general_administrator(user):
        return None

    profile = getattr(user, "profile", None)
    if profile is None or profile.delegation_id is None:
        return set()

    role_delegations = set(
        RoleScope.objects.filter(group__user=user).values_list(
            "delegations__pk",
            flat=True,
        )
    )
    role_delegations.discard(None)

    if not role_delegations:
        return {profile.delegation_id}

    return {profile.delegation_id}.intersection(role_delegations)
