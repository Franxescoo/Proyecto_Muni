"""Regla común de detección de metas cuantitativas medidas por atenciones.

El nombre/unidad del ítem identifica el tipo de medición sin migrar la BD.
Metas porcentuales conservan su fórmula; el objetivo cuantitativo contiene
las atenciones requeridas. Un registro sin referencia al ítem mantiene su
nombre histórico. No se cuentan evidencias para el avance de estas metas.
"""
import re
import unicodedata


def _normalized(value):
    value = unicodedata.normalize('NFKD', str(value or '').casefold())
    return ''.join(c for c in value if not unicodedata.combining(c))


def is_attention_measure(*, name='', unit='', item_type='quantitative'):
    if item_type == 'percentage':
        return False
    return bool(re.search(r'\batencion(?:es)?\b', _normalized(name) + ' ' + _normalized(unit)))


def goal_is_attention(goal):
    item = getattr(goal, 'measurement_item', None)
    if item is not None and getattr(item, 'item_type', '') == 'percentage':
        return False
    names = (getattr(goal, 'item', ''), getattr(goal, 'unit', ''),
             getattr(item, 'name', '') if item else '',
             getattr(item, 'unit', '') if item else '')
    return is_attention_measure(name=' '.join(str(x or '') for x in names))


def goal_uses_resolved_attentions(goal):
    """Regla nueva para metas cuantitativas.

    El objetivo efectivo es el número de atenciones RESUELTAS/CERRADAS
    distintas vinculadas a actividades computables. Los ítems porcentuales
    mantienen exactamente su fórmula. Metas legacy con unidad porcentual
    sin item asociado también conservan su cálculo anterior.
    """
    item = getattr(goal, 'measurement_item', None)
    if item is not None:
        return getattr(item, 'item_type', '') != 'percentage'
    unit = _normalized(getattr(goal, 'unit', ''))
    if '%' in unit or unit.strip() in ('porcentaje', 'porcentajes', 'percent', 'percentage'):
        return False
    return True
