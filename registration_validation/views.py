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

from .forms import (
    ActivityForm,
    EvidenceForm,
)
from .models import (
    Activity,
    Evidence,
)


# ---------------------------------------------------------
# Utilidades de Activity
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
# Utilidades de Evidence
# ---------------------------------------------------------


def scoped_evidences(user):
    """
    Retorna únicamente las evidencias visibles para
    el usuario según la delegación de su actividad.
    """

    evidences = (
        Evidence.objects
        .filter(
            deleted_at__isnull=True,
            activity__deleted_at__isnull=True,
            activity__goal__deleted_at__isnull=True,
            activity__goal__period__deleted_at__isnull=True,
        )
        .select_related(
            "activity",
            "activity__goal",
            "activity__goal__period",
            "activity__author",
            "activity__author__delegation",
            "author",
            "author__delegation",
        )
    )

    if user.is_superuser:
        return evidences

    profile = getattr(
        user,
        "profile",
        None,
    )

    if (
        profile is None
        or profile.delegation_id is None
    ):
        return evidences.none()

    return evidences.filter(
        activity__author__delegation_id=(
            profile.delegation_id
        ),
    )


def ensure_evidence_editable(evidence):
    """
    Impide modificar o eliminar una evidencia cuando
    su actividad, meta o período no permite cambios.
    """

    activity = evidence.activity
    goal = activity.goal
    period = goal.period

    if activity.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una evidencia cuya "
            "actividad se encuentra eliminada."
        )

    if goal.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una evidencia cuya "
            "meta se encuentra archivada."
        )

    if period.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una evidencia asociada "
            "a un período archivado."
        )

    if period.status == Period.Status.CLOSED:
        raise PermissionDenied(
            "El período está cerrado. "
            "Las evidencias asociadas solo pueden "
            "consultarse."
        )


def filtered_evidences(request):
    """
    Aplica búsqueda y filtro por estado de revisión
    sobre las evidencias visibles para el usuario.
    """

    evidences = scoped_evidences(
        request.user,
    )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    review_status = request.GET.get(
        "review_status",
        "",
    ).strip()

    if query:
        evidences = evidences.filter(
            Q(
                code__icontains=query
            )
            | Q(
                activity__request_problem__icontains=query
            )
            | Q(
                activity__goal__item__icontains=query
            )
            | Q(
                author__name__icontains=query
            )
            | Q(
                file_link__icontains=query
            )
        )

    if review_status:
        evidences = evidences.filter(
            review_status=review_status,
        )

    return evidences.order_by(
        "-date",
        "evidence_id",
    )


def evidence_status_options(user):
    """
    Obtiene los estados de revisión que realmente
    existen en los registros visibles.

    No se inventan estados que no estén definidos
    actualmente en los datos del proyecto.
    """

    return list(
        scoped_evidences(user)
        .exclude(
            review_status="",
        )
        .values_list(
            "review_status",
            flat=True,
        )
        .distinct()
        .order_by(
            "review_status",
        )
    )


# ---------------------------------------------------------
# Mixins reutilizables de Activity
# ---------------------------------------------------------


class ActivityPermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    """
    Exige autenticación y el permiso definido
    por cada vista de Activity.
    """

    login_url = "login"
    raise_exception = True

    def handle_no_permission(self):
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
    Entrega request.user al ActivityForm.
    """

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs["user"] = self.request.user

        return kwargs


class ActivityPageContextMixin:
    """
    Permite que Create y Update reutilicen
    el listado y el modal.
    """

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs,
        )

        context["activities"] = (
            filtered_activities(
                self.request,
            )
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
# Mixins reutilizables de Evidence
# ---------------------------------------------------------


class EvidencePermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    """
    Exige autenticación y permiso para las vistas
    relacionadas con Evidence.
    """

    login_url = "login"
    raise_exception = True

    def handle_no_permission(self):
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


class EvidenceScopeMixin:
    """
    Aplica scoping por delegación a operaciones
    sobre una Evidence existente.
    """

    def get_queryset(self):
        return scoped_evidences(
            self.request.user,
        )


class EvidenceFormMixin:
    """
    Entrega request.user al EvidenceForm.
    """

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs["user"] = self.request.user

        return kwargs


class EvidencePageContextMixin:
    """
    Permite reutilizar la página de evidencias
    para Create y Update.
    """

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs,
        )

        context["evidences"] = (
            filtered_evidences(
                self.request,
            )
        )

        context["query"] = (
            self.request.GET.get(
                "q",
                "",
            ).strip()
        )

        context["selected_review_status"] = (
            self.request.GET.get(
                "review_status",
                "",
            ).strip()
        )

        context["review_status_options"] = (
            evidence_status_options(
                self.request.user,
            )
        )

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
            "Actividad eliminada correctamente.",
        )

        return HttpResponseRedirect(
            self.get_success_url(),
        )


# ---------------------------------------------------------
# CRUD de Evidence
# ---------------------------------------------------------


class EvidenceListView(
    EvidencePermissionMixin,
    ListView,
):
    model = Evidence

    permission_required = (
        "registration_validation.view_evidence"
    )

    template_name = (
        "registration_validation/"
        "evidence_list.html"
    )

    context_object_name = "evidences"

    paginate_by = 25

    def get_queryset(self):
        return filtered_evidences(
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

        context["selected_review_status"] = (
            self.request.GET.get(
                "review_status",
                "",
            ).strip()
        )

        context["review_status_options"] = (
            evidence_status_options(
                self.request.user,
            )
        )

        return context


class EvidenceCreateView(
    EvidencePermissionMixin,
    EvidenceFormMixin,
    EvidencePageContextMixin,
    CreateView,
):
    model = Evidence

    form_class = EvidenceForm

    permission_required = (
        "registration_validation.add_evidence"
    )

    template_name = (
        "registration_validation/"
        "evidence_list.html"
    )

    success_url = reverse_lazy(
        "registration:evidence_list"
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
            "Evidencia creada correctamente.",
        )

        return response


class EvidenceUpdateView(
    EvidencePermissionMixin,
    EvidenceScopeMixin,
    EvidenceFormMixin,
    EvidencePageContextMixin,
    UpdateView,
):
    model = Evidence

    form_class = EvidenceForm

    permission_required = (
        "registration_validation.change_evidence"
    )

    template_name = (
        "registration_validation/"
        "evidence_list.html"
    )

    pk_url_kwarg = "evidence_id"

    success_url = reverse_lazy(
        "registration:evidence_list"
    )

    def get_object(
        self,
        queryset=None,
    ):
        evidence = super().get_object(
            queryset,
        )

        ensure_evidence_editable(
            evidence,
        )

        return evidence

    def form_valid(
        self,
        form,
    ):
        response = super().form_valid(
            form,
        )

        messages.success(
            self.request,
            "Evidencia actualizada correctamente.",
        )

        return response


class EvidenceDeleteView(
    EvidencePermissionMixin,
    EvidenceScopeMixin,
    DeleteView,
):
    model = Evidence

    permission_required = (
        "registration_validation.delete_evidence"
    )

    pk_url_kwarg = "evidence_id"

    success_url = reverse_lazy(
        "registration:evidence_list"
    )

    http_method_names = [
        "post",
    ]

    def get_object(
        self,
        queryset=None,
    ):
        evidence = super().get_object(
            queryset,
        )

        ensure_evidence_editable(
            evidence,
        )

        return evidence

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
            "Evidencia eliminada correctamente.",
        )

        return HttpResponseRedirect(
            self.get_success_url(),
        )