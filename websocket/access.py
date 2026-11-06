"""Autorización del chat por la delegación activa del funcionario."""

from accounts.delegation_context import authorized_delegations


def chat_delegation_id(user, selected_id=None):
    """Devuelve una delegación autorizada o None; nunca confía en IDs del cliente."""
    if not user.is_authenticated or not user.is_active or user.is_superuser:
        return None
    choices = authorized_delegations(user)
    if not choices:
        return None
    ids = {item.pk for item in choices}
    if selected_id is not None:
        try:
            selected_id = int(selected_id)
        except (ValueError, TypeError):
            return None
        return selected_id if selected_id in ids else None
    # Fallback del mismo criterio que usa ActiveDelegationMiddleware.
    primary = getattr(getattr(user, "profile", None), "delegation_id", None)
    return primary if primary in ids else choices[0].pk
