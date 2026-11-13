"""Fórmulas porcentuales admitidas por el motor de Monitoreo.

Las fórmulas se identifican por texto canónico y no se ejecutan como código.
"""
SUPPORTED_PERCENTAGE_FORMULA = (
    "(actividades aprobadas / actividades registradas) * 100"
)
SUPPORTED_PERCENTAGE_FORMULAS = (
    SUPPORTED_PERCENTAGE_FORMULA,
    "(atenciones completadas / atenciones registradas) * 100",
    "(solicitudes resueltas / solicitudes registradas) * 100",
)

_FORMULA_KINDS = {
    SUPPORTED_PERCENTAGE_FORMULA: "approved_activities",
    SUPPORTED_PERCENTAGE_FORMULAS[1]: "completed_attentions",
    SUPPORTED_PERCENTAGE_FORMULAS[2]: "resolved_requests",
}


def canonical_percentage_formula(value):
    value = " ".join((value or "").casefold().replace("×", "*").split())
    return value if value in _FORMULA_KINDS else None


def percentage_formula_kind(value):
    """Return the closed-set metric name for a validated formula."""
    canonical = canonical_percentage_formula(value)
    return _FORMULA_KINDS.get(canonical)
