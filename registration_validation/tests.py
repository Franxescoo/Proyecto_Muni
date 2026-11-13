from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .views import (
    ActivityListView,
    REGISTRATION_PAGE_SIZE_SESSION_KEY,
)


class RegistrationPageSizeTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="registration-page-size",
            password="test-password",
        )
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=("is_superuser", "is_staff"))
        self.client.force_login(user)

    def test_preference_is_saved_and_redirects_to_current_filtered_list(self):
        response = self.client.post(
            reverse("registration:set_page_size"),
            {
                "page_size": "50",
                "next": "/registration/activities/?q=reports",
            },
        )

        self.assertRedirects(
            response,
            "/registration/activities/?q=reports",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session[REGISTRATION_PAGE_SIZE_SESSION_KEY],
            50,
        )

    def test_list_uses_saved_page_size(self):
        request = RequestFactory().get(
            "/registration/activities/",
        )
        request.session = {
            REGISTRATION_PAGE_SIZE_SESSION_KEY: 50,
        }
        view = ActivityListView()
        view.request = request

        self.assertEqual(view.get_paginate_by(None), 50)

    def test_registration_lists_render_sidebar_and_page_size_selector(self):
        list_routes = (
            ("registration:activity_list", "activity-page-size", "Actividades"),
            ("registration:evidence_list", "evidence-page-size", "Evidencias"),
            ("registration:validation_list", "validation-page-size", "Validaciones"),
        )

        for route_name, selector_id, guide_section in list_routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Registro y validación")
                self.assertContains(response, "Inicio")
                self.assertContains(response, "Gestión de accesos")
                self.assertContains(response, "registration_validation_help.js")
                self.assertContains(response, "registration_validation_help.css")
                self.assertContains(response, selector_id)
                self.assertContains(response, "Guardar preferencia")
                self.assertContains(response, 'data-sgr-help-module="registration_validation"')
                self.assertContains(response, "Iniciar tutorial")
                self.assertContains(response, "Mostrar guía lateral")
                self.assertContains(response, 'data-sgr-guide-rail')
                self.assertContains(response, 'id="registrationHelpOffcanvas"')
                self.assertContains(response, guide_section)

        response = self.client.get(reverse("registration:attention_entry_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingreso de atención")
        self.assertContains(response, "historial de movimientos en orden cronológico")

    def test_create_forms_render_their_contextual_tutorial_trigger(self):
        form_routes = (
            ("registration:attention_entry_create", "attentionEntryModal"),
            ("registration:activity_create", "activityModal"),
            ("registration:evidence_create", "evidenceModal"),
            ("registration:validation_create", "validationModal"),
            ("registration:service_create", "serviceModal"),
            ("registration:activity_type_create", "activityTypeModal"),
            ("registration:attention_type_create", "attentionTypeModal"),
            ("registration:sub_attention_create", "subAttentionModal"),
        )

        for route_name, modal_id in form_routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    f'data-sgr-autohelp="registration:{route_name.split(":")[1]}"',
                )
                self.assertContains(response, f'id="{modal_id}"')
                self.assertContains(response, "Iniciar tutorial")

    def test_unsupported_page_size_is_not_saved(self):
        response = self.client.post(
            reverse("registration:set_page_size"),
            {
                "page_size": "100",
                "next": "/registration/activities/",
            },
        )

        self.assertRedirects(
            response,
            "/registration/activities/",
            fetch_redirect_response=False,
        )
        self.assertNotIn(
            REGISTRATION_PAGE_SIZE_SESSION_KEY,
            self.client.session,
        )
