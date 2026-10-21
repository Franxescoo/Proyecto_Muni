"""Pruebas de presentación, sin modificar las reglas de negocio ni la base de datos."""
from django import forms
from django.template.loader import get_template, render_to_string
from django.test import SimpleTestCase


class DummyForm(forms.Form):
    name = forms.CharField(label="Nombre")
    employee = forms.ChoiceField(choices=[("1", "Ejemplo")], label="Empleado")
    measurement_item = forms.CharField(label="Ítem")


class MunicipalModalPresentationTests(SimpleTestCase):
    def test_organization_view_only_has_close_and_no_save(self):
        output = render_to_string("organization/_record_modal.html", {
            "form": DummyForm(), "form_route": "organization:employee_list",
            "modal_action": "view", "modal_title": "Ver empleado", "object_id": "1",
        })
        self.assertIn("sgr-upgraded-modal", output)
        self.assertIn("Cerrar", output)
        self.assertNotIn('type="submit"', output)

    def test_organization_edit_retains_save_action(self):
        output = render_to_string("organization/_record_modal.html", {
            "form": DummyForm(), "form_route": "organization:employee_list",
            "modal_action": "edit", "modal_title": "Modificar empleado", "object_id": "1",
        })
        self.assertIn('type="submit"', output)
        self.assertIn('value="edit"', output)
        self.assertIn('name="object_id"', output)

    def test_goal_view_has_only_close_no_save(self):
        output = render_to_string("planning/_goal_modal.html", {
            "open_modal": True, "title": "Ver meta", "form": DummyForm(),
            "readonly": True, "modal_action": "/metas/",
        })
        self.assertIn("sgr-upgraded-modal", output)
        self.assertIn("Cerrar", output)
        self.assertNotIn('type="submit"', output)

    def test_goal_edit_retains_special_save_buttons(self):
        output = render_to_string("planning/_goal_modal.html", {
            "open_modal": True, "title": "Editar meta", "form": DummyForm(),
            "readonly": False, "modal_action": "/metas/",
        })
        self.assertIn('name="_addanother"', output)
        self.assertIn('name="_continue"', output)
        self.assertIn('name="_save"', output)

    def test_all_municipal_modal_templates_compile(self):
        names = (
            "organization/_record_modal.html", "planning/_goal_modal.html",
            "planning/_period_modal.html", "planning/item_form.html",
            "planning/goal_form.html",
            "registration_validation/_activity_modal.html",
            "registration_validation/_activity_type_modal.html",
            "registration_validation/_attention_type_modal.html",
            "registration_validation/_service_modal.html",
            "registration_validation/_evidence_modal.html",
            "registration_validation/_validation_modal.html",
            "registration_validation/attention_entry_list.html",
            "registration_validation/sub_attention_list.html",
        )
        for name in names:
            with self.subTest(name=name):
                get_template(name)
