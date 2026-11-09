"""Utilidades para validar RUT chileno; nunca consultan servicios externos."""
import re
from django.core.exceptions import ValidationError


def normalize_rut(value):
    return re.sub(r"[.\-\s]", "", (value or "")).upper()


def validate_rut(value):
    value = normalize_rut(value)
    if not re.fullmatch(r"\d{1,8}[\dK]", value) or int(value[:-1]) == 0:
        raise ValidationError("Ingresa un RUT chileno válido con su dígito verificador.")
    s = sum(int(n) * (2 + i % 6) for i, n in enumerate(reversed(value[:-1])))
    check = 11 - s % 11
    digit = "0" if check == 11 else "K" if check == 10 else str(check)
    if value[-1] != digit:
        raise ValidationError("El dígito verificador del RUT no es válido.")


def format_rut(rut):
    value = normalize_rut(rut)
    return f"{int(value[:-1]):,}".replace(",", ".") + "-" + value[-1] if len(value) > 1 and value[:-1].isdigit() else value
