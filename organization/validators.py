import re

from django.core.exceptions import ValidationError


def normalize_rut(value):
    """Return a Chilean RUT in canonical format: 12.345.678-5 or -K."""
    raw = (value or "").strip().upper()
    if not re.fullmatch(r"[0-9.\-\sK]+", raw):
        raise ValidationError(
            "El RUT solo puede contener números, K, puntos y guion."
        )
    compact = re.sub(r"[^0-9K]", "", raw)
    if len(compact) < 2:
        raise ValidationError("Ingresa un RUT válido.")

    body, verifier = compact[:-1], compact[-1]
    if not body.isdigit() or not 1 <= len(body) <= 8:
        raise ValidationError("El RUT debe tener entre 1 y 8 dígitos.")

    total = 0
    multiplier = 2
    for digit in reversed(body):
        total += int(digit) * multiplier
        multiplier = 2 if multiplier == 7 else multiplier + 1

    expected = 11 - (total % 11)
    expected_verifier = (
        "K" if expected == 10
        else "0" if expected == 11
        else str(expected)
    )
    if verifier != expected_verifier:
        raise ValidationError("El dígito verificador del RUT no es válido.")

    formatted_body = f"{int(body):,}".replace(",", ".")
    return f"{formatted_body}-{verifier}"
