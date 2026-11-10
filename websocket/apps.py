from django.apps import AppConfig


class WebsocketConfig(AppConfig):
    name = 'websocket'

    def ready(self):
        from .live import connect_live_signals

        connect_live_signals()
