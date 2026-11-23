from django.shortcuts import redirect
from django.urls import reverse


class FirstLoginPasswordChangeMiddleware:
    """Impide navegar por el SGR con la clave temporal aún activa.

    Se instala justo después de AuthenticationMiddleware, antes de ejecutar
    lógica de delegaciones u otros módulos.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            if profile is not None and getattr(profile, 'must_change_password', False):
                target = reverse('accounts:first_login_password_change')
                path = request.path_info
                # Permitir cambio de clave, cierre de sesión, recuperación de
                # acceso y recursos estáticos. No exponer otros módulos.
                allowed = (
                    path == target
                    or path == '/accounts/logout/'
                    or path.startswith('/accounts/password_reset/')
                    or path.startswith('/static/')
                    or path.startswith('/media/')
                )
                if not allowed:
                    return redirect(target)
        return self.get_response(request)
