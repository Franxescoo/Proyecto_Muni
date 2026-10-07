from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from .modules import MODULES

# Colores de las tarjetas (se repiten en ciclo)
TILE_COLORS = ["pink", "orange", "salmon", "yellow", "green", "blue", "indigo"]


def build_sections(user):
    """Arma las secciones con las tarjetas que el usuario puede ver."""
    sections = []
    index = 0
    for section in MODULES:
        cards = []
        for card in section["cards"]:
            permission = card.get("perm")
            if permission and not user.has_perm(permission):
                continue
            try:
                href = reverse(card["url"])
            except NoReverseMatch:
                href = None  # el módulo aún no define esa ruta
            cards.append(
                {
                    **card,
                    "href": href,
                    "color": TILE_COLORS[index % len(TILE_COLORS)],
                }
            )
            index += 1
        if cards:
            sections.append({"title": section["title"], "cards": cards})
    return sections


@login_required
def home(request):
    # Valor temporal en la sesión: visitas a la página principal
    visits = request.session.get("home_visits", 0) + 1
    request.session["home_visits"] = visits

    profile = getattr(request.user, "profile", None)
    delegation = profile.delegation if profile and profile.delegation_id else None

    context = {
        "sections": build_sections(request.user),
        "delegation": delegation,
        "visits": visits,
    }
    return render(request, "home.html", context)
