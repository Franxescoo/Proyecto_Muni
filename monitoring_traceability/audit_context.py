
from contextvars import ContextVar

_current_user = ContextVar("sgr_audit_user", default=None)


def get_audit_user():
    return _current_user.get()


class AuditUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if request.user.is_authenticated else None
        token = _current_user.set(user)

        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)
