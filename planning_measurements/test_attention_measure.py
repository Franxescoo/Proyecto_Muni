"""Pruebas unitarias de la clasificación de metas por atenciones."""
from types import SimpleNamespace
from django.test import SimpleTestCase
from .attention_measure import goal_is_attention, is_attention_measure


class GoalAttentionMeasurementTests(SimpleTestCase):
    def test_atenciones_plural(self):
        self.assertTrue(is_attention_measure(name='Atenciones registradas'))

    def test_atencion_singular(self):
        self.assertTrue(is_attention_measure(name='Atención ciudadana'))

    def test_en_unidad(self):
        self.assertTrue(is_attention_measure(unit='atenciones'))

    def test_actividades_no_son_atenciones(self):
        self.assertFalse(is_attention_measure(name='Actividades registradas'))

    def test_meta_porcentual_conserva_formula(self):
        item = SimpleNamespace(name='Atenciones', unit='%', item_type='percentage')
        goal = SimpleNamespace(item='Atenciones', unit='%', measurement_item=item)
        self.assertFalse(goal_is_attention(goal))

    def test_meta_cuantitativa_medida_por_atenciones(self):
        item = SimpleNamespace(name='Atenciones resueltas', unit='atenciones', item_type='quantitative')
        goal = SimpleNamespace(item='Atenciones resueltas', unit='atenciones', measurement_item=item)
        self.assertTrue(goal_is_attention(goal))
