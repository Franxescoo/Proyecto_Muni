"""Motor de expresiones medibles compartido por Planificación y Monitoreo.

No evalúa código Python, ni expresiones SQL ni acceso a atributos. Se pueden
combinar las variables publicadas mediante operaciones aritméticas seguras.
Al añadir un origen de datos nuevo se registra su variable en el catálogo.
"""

import ast
import re
import unicodedata
from decimal import Decimal, DivisionByZero, InvalidOperation

from django.core.exceptions import ValidationError

# Alias históricos, que deben seguir funcionando sin cambiar metas existentes.
SUPPORTED_PERCENTAGE_FORMULA = "(actividades aprobadas / actividades registradas) * 100"
SUPPORTED_PERCENTAGE_FORMULAS = (
    SUPPORTED_PERCENTAGE_FORMULA,
    "(atenciones completadas / atenciones registradas) * 100",
    "(solicitudes resueltas / solicitudes registradas) * 100",
)

# Variables disponibles y descripción de origen de sus datos.
FORMULA_VARIABLES = {
    "actividades_registradas": "Actividades registradas en esta meta y período",
    "actividades_aprobadas": "Actividades con evidencia validada en esta meta",
    "evidencias_aprobadas": "Evidencias aprobadas de las actividades de esta meta",
    "atenciones_registradas": "Atenciones distintas asociadas a las actividades de esta meta",
    "atenciones_completadas": "Atenciones distintas resueltas o cerradas",
    "solicitudes_registradas": "Solicitudes distintas vinculadas a las atenciones de esta meta",
    "solicitudes_resueltas": "Solicitudes distintas en estado cerrada",
    "compromisos_registrados": "Compromisos activos vinculados a actividades de esta meta",
    "compromisos_realizados": "Compromisos completados o validados de esta meta",
    "compromisos_validados": "Compromisos validados de esta meta, contados una vez",
    "compromisos_vencidos": "Compromisos vencidos y no finalizados de esta meta",
    "dias_computables": "Días computables del período",
    "dias_transcurridos": "Días computables transcurridos al momento del cálculo",
    "meta_objetivo": "Valor objetivo configurado para la meta",
}

_LEGACY_ALIASES = {
    "actividades aprobadas": "actividades_aprobadas",
    "actividades registradas": "actividades_registradas",
    "atenciones completadas": "atenciones_completadas",
    "atenciones registradas": "atenciones_registradas",
    "total de atenciones": "atenciones_registradas",
    "solicitudes resueltas": "solicitudes_resueltas",
    "solicitudes registradas": "solicitudes_registradas",
    "compromisos validados": "compromisos_validados",
    "compromisos registrados": "compromisos_registrados",
}

_FORMULA_KINDS = dict(zip(SUPPORTED_PERCENTAGE_FORMULAS, (
    "approved_activities", "completed_attentions", "resolved_requests",
)))


class FormulaError(ValueError):
    """La fórmula declarada no es válida o no se puede calcular."""


def _ascii(text):
    return "".join(
        letter for letter in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(letter)
    )


def normalize_formula(value):
    """Normaliza formato y nombres históricos, sin cambiar la operación."""
    expression = _ascii(str(value or "").casefold().replace("×", "*"))
    expression = re.sub(r"(?<=\d),(?=\d)", ".", expression)
    for label, variable in sorted(_LEGACY_ALIASES.items(), key=lambda x: -len(x[0])):
        expression = re.sub(
            r"(?<![\w])" + re.escape(label) + r"(?![\w])",
            variable, expression,
        )
    return " ".join(expression.split())


def _validate_ast(node, variables, depth=0):
    if depth > 32:
        raise FormulaError("La fórmula supera la complejidad permitida.")
    if isinstance(node, ast.Expression):
        return _validate_ast(node.body, variables, depth + 1)
    if isinstance(node, ast.Constant):
        if type(node.value) not in (int, float) or len(str(node.value)) > 18:
            raise FormulaError("Solo se permiten números finitos en la fórmula.")
        return
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise FormulaError(f"Variable no reconocida: {node.id}.")
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _validate_ast(node.operand, variables, depth + 1)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (
        ast.Add, ast.Sub, ast.Mult, ast.Div,
    )):
        _validate_ast(node.left, variables, depth + 1)
        _validate_ast(node.right, variables, depth + 1)
        return
    raise FormulaError(
        "Operación no permitida. Usa variables, números, +, -, *, / y paréntesis."
    )


def validate_formula(value):
    """Devuelve expresión normalizada o lanza FormulaError explicativo."""
    expression = normalize_formula(value)
    if not expression or len(expression) > 500:
        raise FormulaError("La fórmula es obligatoria y no debe superar 500 caracteres.")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise FormulaError("La fórmula tiene un formato matemático incorrecto.") from exc
    _validate_ast(tree, FORMULA_VARIABLES)
    return expression


def canonical_percentage_formula(value):
    """Compatibilidad con validaciones de metas: retorna None si es inválida."""
    try:
        return validate_formula(value)
    except FormulaError:
        return None


def percentage_formula_kind(value):
    """Identificador histórico de las tres expresiones preexistentes."""
    normalized = normalize_formula(value)
    for original, kind in _FORMULA_KINDS.items():
        if normalized == normalize_formula(original):
            return kind
    return None


def evaluate_formula(expression, values):
    """Evalúa sobre Decimal sin acceso a funciones o datos externos."""
    normalized = validate_formula(expression)
    tree = ast.parse(normalized, mode="eval")

    def compute(node):
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            try:
                value = Decimal(str(values[node.id]))
            except (KeyError, TypeError, InvalidOperation) as exc:
                raise FormulaError(f"No hay datos válidos para {node.id}.") from exc
            return value
        if isinstance(node, ast.UnaryOp):
            value = compute(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = compute(node.left), compute(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if not right:
                # Un denominador sin registros representa una proporción de 0%.
                return Decimal("0")
            return left / right
        raise FormulaError("Expresión no permitida.")

    try:
        result = compute(tree.body)
    except (DivisionByZero, InvalidOperation, OverflowError, ArithmeticError) as exc:
        raise FormulaError("No se pudo calcular la fórmula con esos datos.") from exc
    if not result.is_finite() or abs(result) > Decimal("9999999999"):
        raise FormulaError("El resultado de la fórmula está fuera de rango.")
    return result
