from django.test import RequestFactory, SimpleTestCase, override_settings
from django.contrib.auth.models import AnonymousUser

from .error_views import bad_request, page_not_found, permission_denied, server_error


@override_settings(DEBUG=False)
class ErrorHandlerTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")
        self.request.user = AnonymousUser()

    def test_not_found_uses_organization_template(self):
        response = self.client.get("/ruta-que-no-existe/")

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "organization/errors/404.html")
        self.assertContains(response, "Página no encontrada", status_code=404)

    def test_all_handlers_render_their_organization_template(self):
        handlers = (
            (bad_request, 400),
            (permission_denied, 403),
            (page_not_found, 404),
        )
        for handler, status_code in handlers:
            with self.subTest(status_code=status_code):
                response = handler(self.request, Exception())
                self.assertEqual(response.status_code, status_code)
                self.assertIn(str(status_code).encode(), response.content)

        response = server_error(self.request)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"500", response.content)

    @override_settings(DEBUG=True)
    def test_error_preview_is_available_in_debug(self):
        response = self.client.get("/organization/errores/403/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Volver al inicio")
        self.assertContains(response, "Volver atrás")

    @override_settings(DEBUG=True)
    def test_unknown_module_route_uses_custom_template_in_debug(self):
        response = self.client.get("/planning/ruta-que-no-existe/")

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "organization/errors/404.html")
        self.assertContains(response, "Página no encontrada", status_code=404)
