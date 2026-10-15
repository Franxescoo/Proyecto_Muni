from django.apps import AppConfig


class MonitoringTraceabilityConfig(AppConfig):
    name = 'monitoring_traceability'

    def ready(self):
        from . import signals  # noqa: F401
