from django.conf import settings
from django.http import Http404
from django.shortcuts import render


ERROR_PAGES = {
    400: ("400.html", "Solicitud incorrecta"),
    403: ("403.html", "Acceso denegado"),
    404: ("404.html", "Página no encontrada"),
    500: ("500.html", "Error interno del servidor"),
}


def error_preview(request, error_code):
    if not settings.DEBUG:
        raise Http404
    template_name, error_title = ERROR_PAGES.get(
        error_code,
        ERROR_PAGES[404],
    )
    return render(
        request,
        f"organization/errors/{template_name}",
        {"error_code": error_code, "error_title": error_title},
    )


def bad_request(request, exception):
    return render(
        request,
        "organization/errors/400.html",
        {"error_code": 400, "error_title": "Solicitud incorrecta"},
        status=400,
    )


def permission_denied(request, exception):
    return render(
        request,
        "organization/errors/403.html",
        {"error_code": 403, "error_title": "Acceso denegado"},
        status=403,
    )


def page_not_found(request, exception):
    return render(
        request,
        "organization/errors/404.html",
        {"error_code": 404, "error_title": "Página no encontrada"},
        status=404,
    )


def server_error(request):
    return render(
        request,
        "organization/errors/500.html",
        {"error_code": 500, "error_title": "Error interno del servidor"},
        status=500,
    )
