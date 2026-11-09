from django.apps import AppConfig


class CitizenRequestsConfig(AppConfig):
    name = 'citizen_requests'

    def ready(self):
        from . import signals  # noqa: F401
