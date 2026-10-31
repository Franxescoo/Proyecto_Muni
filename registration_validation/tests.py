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
            ("registration:activity_list", "activity-page-size"),
            ("registration:evidence_list", "evidence-page-size"),
            ("registration:validation_list", "validation-page-size"),
        )

        for route_name, selector_id in list_routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Registro y validación")
                self.assertContains(response, "Inicio")
                self.assertContains(response, "Gestión de accesos")
                self.assertContains(response, selector_id)
                self.assertContains(response, "Guardar preferencia")

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
