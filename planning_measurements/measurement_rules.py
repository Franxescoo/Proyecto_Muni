"""Fórmulas formalmente compatibles con el motor actual de Monitoreo."""
SUPPORTED_PERCENTAGE_FORMULA = (
    "(actividades aprobadas / actividades registradas) * 100"
)


def canonical_percentage_formula(value):
    value = " ".join((value or "").casefold().replace("×", "*").split())
    return SUPPORTED_PERCENTAGE_FORMULA if value == SUPPORTED_PERCENTAGE_FORMULA else None
