from django.contrib import messages
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    UpdateView,
)

from planning_measurements.models import Period

from .forms import ActivityForm
from .models import Activity


# ---------------------------------------------------------
# Utilidades de seguridad y scoping
# ---------------------------------------------------------


def scoped_activities(user):
    """
    Retorna únicamente las actividades que el usuario
    puede visualizar según su delegación.
    """

    activities = (
        Activity.objects
        .filter(
            deleted_at__isnull=True,
            goal__deleted_at__isnull=True,
            goal__period__deleted_at__isnull=True,
        )
        .select_related(
            "goal",
            "goal__period",
            "goal__employee",
            "author",
            "author__delegation",
        )
    )

    if user.is_superuser:
        return activities

    profile = getattr(
        user,
        "profile",
        None,
    )

    if (
        profile is None
        or profile.delegation_id is None
    ):
        return activities.none()

    return activities.filter(
        author__delegation_id=profile.delegation_id,
    )


def ensure_activity_editable(activity):
    """
    Impide modificar o eliminar actividades relacionadas
    con metas o períodos archivados/cerrados.
    """

    goal = activity.goal
    period = goal.period

    if goal.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una actividad cuya "
            "meta se encuentra archivada."
        )

    if period.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una actividad asociada "
            "a un período archivado."
        )

    if period.status == Period.Status.CLOSED:
        raise PermissionDenied(
            "El período está cerrado. "
            "Las actividades asociadas solo pueden "
            "consultarse."
        )


def filtered_activities(request):
    """
    Aplica búsqueda y filtro de estado sobre las
    actividades que el usuario puede visualizar.
    """

    activities = scoped_activities(
        request.user,
    )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    status = request.GET.get(
        "status",
        "",
    ).strip()

    if query:
        activities = activities.filter(
            Q(
                request_problem__icontains=query
            )
            | Q(
                action__icontains=query
            )
            | Q(
                contact__icontains=query
            )
            | Q(
                author__name__icontains=query
            )
            | Q(
                goal__item__icontains=query
            )
        )

    if status:
        activities = activities.filter(
            status=status,
        )

    return activities.order_by(
        "-date",
        "activity_id",
    )


# ---------------------------------------------------------
# Mixins reutilizables
# ---------------------------------------------------------


class ActivityPermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    """
    Exige autenticación y el permiso definido por
    cada vista.
    """

    login_url = "login"
    raise_exception = True

    def handle_no_permission(self):
        """
        Usuario anónimo:
        redirige al login.

        Usuario autenticado sin permiso:
        devuelve 403 Forbidden.
        """

        if self.request.user.is_authenticated:
            raise PermissionDenied(
                "No tienes permisos para realizar "
                "esta operación."
            )

        return redirect_to_login(
            self.request.get_full_path(),
            self.get_login_url(),
            self.get_redirect_field_name(),
        )


class ActivityScopeMixin:
    """
    Aplica scoping por delegación a operaciones
    sobre una Activity existente.
    """

    def get_queryset(self):
        return scoped_activities(
            self.request.user,
        )


class ActivityFormMixin:
    """
    Entrega request.user al ActivityForm para aplicar
    el scoping de Goal y Employee.
    """

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs["user"] = self.request.user

        return kwargs


class ActivityPageContextMixin:
    """
    Permite que Create y Update reutilicen el mismo
    listado y el mismo modal.
    """

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs,
        )

        context["activities"] = filtered_activities(
            self.request,
        )

        context["query"] = (
            self.request.GET.get(
                "q",
                "",
            ).strip()
        )

        context["selected_status"] = (
            self.request.GET.get(
                "status",
                "",
            ).strip()
        )

        context["status_options"] = [
            (
                "Pending",
                "Pendiente",
            ),
            (
                "In progress",
                "En progreso",
            ),
            (
                "Completed",
                "Completada",
            ),
        ]

        context["open_modal"] = True

        return context


# ---------------------------------------------------------
# CRUD de Activity
# ---------------------------------------------------------


class ActivityListView(
    ActivityPermissionMixin,
    ListView,
):
    model = Activity

    permission_required = (
        "registration_validation.view_activity"
    )

    template_name = (
        "registration_validation/"
        "activity_list.html"
    )

    context_object_name = "activities"

    paginate_by = 25

    def get_queryset(self):
        return filtered_activities(
            self.request,
        )

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs,
        )

        context["query"] = (
            self.request.GET.get(
                "q",
                "",
            ).strip()
        )

        context["selected_status"] = (
            self.request.GET.get(
                "status",
                "",
            ).strip()
        )

        context["status_options"] = [
            (
                "Pending",
                "Pendiente",
            ),
            (
                "In progress",
                "En progreso",
            ),
            (
                "Completed",
                "Completada",
            ),
        ]

        return context


class ActivityCreateView(
    ActivityPermissionMixin,
    ActivityFormMixin,
    ActivityPageContextMixin,
    CreateView,
):
    model = Activity

    form_class = ActivityForm

    permission_required = (
        "registration_validation.add_activity"
    )

    template_name = (
        "registration_validation/"
        "activity_list.html"
    )

    success_url = reverse_lazy(
        "registration:activity_list"
    )

    def form_valid(
        self,
        form,
    ):
        response = super().form_valid(
            form,
        )

        messages.success(
            self.request,
            "Actividad creada correctamente.",
        )

        return response


class ActivityUpdateView(
    ActivityPermissionMixin,
    ActivityScopeMixin,
    ActivityFormMixin,
    ActivityPageContextMixin,
    UpdateView,
):
    model = Activity

    form_class = ActivityForm

    permission_required = (
        "registration_validation.change_activity"
    )

    template_name = (
        "registration_validation/"
        "activity_list.html"
    )

    pk_url_kwarg = "activity_id"

    success_url = reverse_lazy(
        "registration:activity_list"
    )

    def get_object(
        self,
        queryset=None,
    ):
        activity = super().get_object(
            queryset,
        )

        ensure_activity_editable(
            activity,
        )

        return activity

    def form_valid(
        self,
        form,
    ):
        response = super().form_valid(
            form,
        )

        messages.success(
            self.request,
            "Actividad actualizada correctamente.",
        )

        return response


class ActivityDeleteView(
    ActivityPermissionMixin,
    ActivityScopeMixin,
    DeleteView,
):
    model = Activity

    permission_required = (
        "registration_validation.delete_activity"
    )

    pk_url_kwarg = "activity_id"

    success_url = reverse_lazy(
        "registration:activity_list"
    )

    # Solo se permite eliminar/archivar mediante POST.
    http_method_names = [
        "post",
    ]

    def get_object(
        self,
        queryset=None,
    ):
        activity = super().get_object(
            queryset,
        )

        ensure_activity_editable(
            activity,
        )

        return activity

    def form_valid(
        self,
        form,
    ):
        now = timezone.now()

        # Borrado lógico.
        self.object.deleted_at = now

        self.object.save(
            update_fields=[
                "deleted_at",
                "updated_at",
            ],
        )

        messages.success(
            self.request,
            "Actividad archivada correctamente.",
        )

        return HttpResponseRedirect(
            self.get_success_url(),
        )