"""Pruebas estructurales del modelo 1 Actividad -> N Atenciones."""
from types import SimpleNamespace
from django.test import SimpleTestCase
from django import forms
from registration_validation.models import Activity, AttentionEntry
from registration_validation.forms import ActivityForm, AttentionEntryForm
from monitoring_traceability.services import activity_attention_ids


class MultiAttentionStructureTests(SimpleTestCase):
    def test_attention_has_one_activity_principal(self):
        field = AttentionEntry._meta.get_field('activity')
        self.assertEqual(field.many_to_one, True)
        self.assertEqual(field.remote_field.related_name, 'assigned_attentions')

    def test_activity_uses_multiple_checkbox_selector(self):
        field = ActivityForm.base_fields['attentions']
        self.assertIsInstance(field, forms.ModelMultipleChoiceField)
        self.assertIsInstance(field.widget, forms.CheckboxSelectMultiple)
        self.assertFalse(field.required)

    def test_attention_has_activity_selector(self):
        self.assertIn('activity', AttentionEntryForm.base_fields)

    def test_no_duplicate_attention_when_legacy_and_current_match(self):
        attention = SimpleNamespace(pk=15, deleted_at=None, activity_id=4)
        activity = SimpleNamespace(
            pk=4, attention_id=15, attention=attention,
            assigned_attentions=SimpleNamespace(all=lambda: [attention]),
        )
        self.assertEqual(activity_attention_ids(activity), {15})
