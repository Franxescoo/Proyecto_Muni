from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    UpdateView,
)
from citizen_requests.models import CitizenRequest, RequestEvent
from citizen_requests.notifications import send_request_state_notification
from citizen_requests.tracking import tracking_stages
from citizen_requests.email_verification import reset_followup_email, schedule_verification
from citizen_registry.models import Citizen
from citizen_registry.forms import CitizenForm
from organization.exports import workbook_response
from accounts.permissions import allowed_delegation_ids
from organization.models import Delegation
from planning_measurements.models import Period
from .forms import (
    ActivityForm,
    AttentionTypeForm,
    AttentionEntryForm,
    SubAttentionForm,
    EvidenceForm,
    ValidationForm,
    ActivityTypeForm,
    ServiceForm,
)
from .models import (
    Activity,
    AttentionEntry,
    AttentionType,
    ActivityType,
    Evidence,
    EvidenceFile,
    SubAttention,
    Validation,
    Service,
)


REGISTRATION_PAGE_SIZE = 25
REGISTRATION_PAGE_SIZE_OPTIONS = (10, 25, 50)


REGISTRATION_PAGE_SIZE_SESSION_KEY = "registration_page_size"


def registration_page_size_context(request):
    size = request.session.get(
        REGISTRATION_PAGE_SIZE_SESSION_KEY,
        REGISTRATION_PAGE_SIZE,
    )
    if size not in REGISTRATION_PAGE_SIZE_OPTIONS:
        size = REGISTRATION_PAGE_SIZE
    return {
        "page_size": size,
        "page_size_options": REGISTRATION_PAGE_SIZE_OPTIONS,
    }
@login_required
@require_POST


def set_page_size(request):
    try:
        size = int(request.POST.get("page_size", ""))
    except (TypeError, ValueError):
        size = None
    if size in REGISTRATION_PAGE_SIZE_OPTIONS:
        request.session[REGISTRATION_PAGE_SIZE_SESSION_KEY] = size
        messages.success(
            request,
            "Preferencia de visualización actualizada.",
        )
    else:
        messages.error(
            request,
            "Valor no válido para registros por página.",
        )
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = reverse("home")
    return redirect(next_url)


# ---------------------------------------------------------
# Utilidades de Activity
# ---------------------------------------------------------


def scoped_activities(user, permission="registration_validation.view_activity"):
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
    allowed_ids = allowed_delegation_ids(user, permission)
    if not allowed_ids:
        return activities.none()
    return activities.filter(
        author__delegation_id__in=allowed_ids,
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


def activity_metrics(user):
    """
    Métricas visibles de actividades según el alcance
    autorizado del usuario.
    """
    activities = scoped_activities(user)
    return {
        "total_activities": activities.count(),
        "pending_activities": activities.filter(
            status="Pending",
        ).count(),
        "completed_activities": activities.filter(
            status="Completed",
        ).count(),
    }


# ---------------------------------------------------------
# Utilidades de Evidence


# ---------------------------------------------------------


def scoped_evidences(user, permission="registration_validation.view_evidence"):
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
    allowed_ids = allowed_delegation_ids(user, permission)
    if not allowed_ids:
        return evidences.none()
    return evidences.filter(
        activity__author__delegation_id__in=allowed_ids,
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


def evidence_metrics(user):
    """
    Estadísticas visibles para el usuario. Se cuentan tanto
    los adjuntos nuevos como el campo de archivo antiguo.
    """
    evidences = scoped_evidences(user)

    evidences_with_file = (
        evidences
        .filter(
            Q(file__isnull=False) & ~Q(file="")
            | Q(
                files__evidence_file_id__isnull=False,
                files__deleted_at__isnull=True,
            )
        )
        .distinct()
        .count()
    )

    return {
        "total_evidences": evidences.count(),
        "pending_evidences": evidences.filter(
            review_status__iexact="Pending",
        ).count(),
        "evidences_with_file": evidences_with_file,
    }


def save_evidence_files(evidence, form):
    """
    Sincroniza los archivos ya validados por EvidenceForm.

    Convierte la referencia antigua Evidence.file en una fila
    de EvidenceFile sin duplicar el archivo físico. Los archivos
    retirados se archivan lógicamente (no se borran del disco).
    Esta función debe ejecutarse dentro de transaction.atomic().
    """
    if evidence.file:
        legacy_path = evidence.file.name

        # Consultamos también las filas archivadas para evitar
        # recrear un adjunto que ya existió con esa ruta.
        if not EvidenceFile.objects.filter(
            evidence=evidence,
            file=legacy_path,
        ).exists():
            EvidenceFile.objects.create(
                evidence=evidence,
                file=legacy_path,
            )

        # El archivo continúa en almacenamiento; solamente
        # dejamos de utilizar el antiguo campo único.
        evidence.file = None
        evidence.save(update_fields=["file", "updated_at"])

    now = timezone.now()

    for existing_file in form.files_to_remove:
        # La comprobación de pertenencia se hizo en form.clean();
        # se vuelve a restringir aquí para no afectar a otras evidencias.
        if (
            existing_file.evidence_id == evidence.pk
            and existing_file.deleted_at is None
        ):
            existing_file.deleted_at = now
            existing_file.save(
                update_fields=["deleted_at", "updated_at"],
            )

    for uploaded_file in form.cleaned_data.get("new_files", []):
        attachment = EvidenceFile(
            evidence=evidence,
            file=uploaded_file,
        )
        attachment.full_clean()
        attachment.save()


# ---------------------------------------------------------
# Utilidades de Validation


# ---------------------------------------------------------


def scoped_validations(user, permission="registration_validation.view_validation"):
    """
    Retorna únicamente las validaciones visibles para
    el usuario según la delegación de la actividad
    asociada a su evidencia.
    """
    validations = (
        Validation.objects
        .filter(
            deleted_at__isnull=True,
            evidence__deleted_at__isnull=True,
            evidence__activity__deleted_at__isnull=True,
            evidence__activity__goal__deleted_at__isnull=True,
            evidence__activity__goal__period__deleted_at__isnull=True,
        )
        .select_related(
            "evidence",
            "evidence__activity",
            "evidence__activity__goal",
            "evidence__activity__goal__period",
            "evidence__activity__author",
            "evidence__activity__author__delegation",
            "verifier",
            "verifier__delegation",
        )
    )
    if user.is_superuser:
        return validations
    allowed_ids = allowed_delegation_ids(user, permission)
    if not allowed_ids:
        return validations.none()
    return validations.filter(
        evidence__activity__author__delegation_id__in=allowed_ids,
    )


def ensure_validation_editable(validation):
    """
    Impide modificar o eliminar una validación cuando
    la evidencia, actividad, meta o período asociado
    no permite cambios.
    """
    evidence = validation.evidence
    activity = evidence.activity
    goal = activity.goal
    period = goal.period
    if evidence.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una validación cuya "
            "evidencia se encuentra eliminada."
        )
    if activity.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una validación cuya "
            "actividad se encuentra eliminada."
        )
    if goal.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una validación cuya "
            "meta se encuentra archivada."
        )
    if period.deleted_at is not None:
        raise PermissionDenied(
            "No puedes modificar una validación asociada "
            "a un período archivado."
        )
    if period.status == Period.Status.CLOSED:
        raise PermissionDenied(
            "El período está cerrado. "
            "Las validaciones asociadas solo pueden "
            "consultarse."
        )


def filtered_validations(request):
    """
    Aplica búsqueda sobre las validaciones visibles
    para el usuario.
    """
    validations = scoped_validations(
        request.user,
    )
    query = request.GET.get(
        "q",
        "",
    ).strip()
    if query:
        validations = validations.filter(
            Q(
                evidence__code__icontains=query
            )
            | Q(
                verifier__name__icontains=query
            )
            | Q(
                decision__icontains=query
            )
            | Q(
                result__icontains=query
            )
            | Q(
                observation__icontains=query
            )
        )
    return validations.order_by(
        "-date",
        "-version",
        "validation_id",
    )


def validation_metrics(user):
    """
    Métricas visibles de validaciones según el alcance
    autorizado del usuario.
    """
    validations = scoped_validations(user)
    last_validation_date = (
        validations
        .order_by("-date")
        .values_list(
            "date",
            flat=True,
        )
        .first()
    )
    reviewed_evidences = (
        validations
        .values(
            "evidence_id",
        )
        .distinct()
        .count()
    )
    return {
        "total_validations": validations.count(),
        "reviewed_evidences": reviewed_evidences,
        "last_validation_date": last_validation_date,
    }


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
            self.request.user, self.permission_required,
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
        context.update(
            activity_metrics(
                self.request.user,
            )
        )
        context.update(
            registration_page_size_context(
                self.request,
            )
        )
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
            self.request.user, self.permission_required,
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
        context.update(
            evidence_metrics(
                self.request.user,
            )
        )
        context.update(
            registration_page_size_context(
                self.request,
            )
        )
        context["open_modal"] = True
        return context


# ---------------------------------------------------------
# Mixins reutilizables de Validation


# ---------------------------------------------------------


class ValidationPermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    """
    Exige autenticación y permiso para las vistas
    relacionadas con Validation.
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


class ValidationScopeMixin:
    """
    Aplica scoping por delegación a operaciones
    sobre una Validation existente.
    """

    def get_queryset(self):
        return scoped_validations(
            self.request.user, self.permission_required,
        )


class ValidationFormMixin:
    """
    Entrega request.user al ValidationForm.
    """

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class ValidationPageContextMixin:
    """
    Permite reutilizar la página de validaciones
    para Create y Update.
    """

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs,
        )
        context["validations"] = (
            filtered_validations(
                self.request,
            )
        )
        context["query"] = (
            self.request.GET.get(
                "q",
                "",
            ).strip()
        )
        context.update(
            validation_metrics(
                self.request.user,
            )
        )
        context.update(
            registration_page_size_context(
                self.request,
            )
        )
        context["open_modal"] = True
        return context


class RegistrationPaginationMixin:
    paginate_by = REGISTRATION_PAGE_SIZE

    def get_page_size(self):
        return registration_page_size_context(
            self.request,
        )["page_size"]

    def get_paginate_by(self, queryset):
        return self.get_page_size()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            registration_page_size_context(
                self.request,
            )
        )
        params = self.request.GET.copy()
        params.pop("page", None)
        context["page_querystring"] = params.urlencode()
        return context


# ---------------------------------------------------------
# CRUD de Activity


# ---------------------------------------------------------


class ActivityListView(
    ActivityPermissionMixin,
    RegistrationPaginationMixin,
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
        context.update(
            activity_metrics(
                self.request.user,
            )
        )
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
    RegistrationPaginationMixin,
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
        context.update(
            evidence_metrics(
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

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save()
            save_evidence_files(self.object, form)

        messages.success(
            self.request,
            "Evidencia creada correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())


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

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save()
            save_evidence_files(self.object, form)

        messages.success(
            self.request,
            "Evidencia actualizada correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())


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


# ---------------------------------------------------------
# CRUD de Validation


# ---------------------------------------------------------


class ValidationListView(
    ValidationPermissionMixin,
    RegistrationPaginationMixin,
    ListView,
):
    model = Validation
    permission_required = (
        "registration_validation.view_validation"
    )
    template_name = (
        "registration_validation/"
        "validation_list.html"
    )
    context_object_name = "validations"
    paginate_by = 25

    def get_queryset(self):
        return filtered_validations(
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
        context.update(
            validation_metrics(
                self.request.user,
            )
        )
        return context


class ValidationCreateView(
    ValidationPermissionMixin,
    ValidationFormMixin,
    ValidationPageContextMixin,
    CreateView,
):
    model = Validation
    form_class = ValidationForm
    permission_required = (
        "registration_validation.add_validation"
    )
    template_name = (
        "registration_validation/"
        "validation_list.html"
    )
    success_url = reverse_lazy(
        "registration:validation_list"
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
            "Validación creada correctamente.",
        )
        return response


class ValidationUpdateView(
    ValidationPermissionMixin,
    ValidationScopeMixin,
    ValidationFormMixin,
    ValidationPageContextMixin,
    UpdateView,
):
    model = Validation
    form_class = ValidationForm
    permission_required = (
        "registration_validation.change_validation"
    )
    template_name = (
        "registration_validation/"
        "validation_list.html"
    )
    pk_url_kwarg = "validation_id"
    success_url = reverse_lazy(
        "registration:validation_list"
    )

    def get_object(
        self,
        queryset=None,
    ):
        validation = super().get_object(
            queryset,
        )
        ensure_validation_editable(
            validation,
        )
        return validation

    def form_valid(
        self,
        form,
    ):
        response = super().form_valid(
            form,
        )
        messages.success(
            self.request,
            "Validación actualizada correctamente.",
        )
        return response


class ValidationDeleteView(
    ValidationPermissionMixin,
    ValidationScopeMixin,
    DeleteView,
):
    model = Validation
    permission_required = (
        "registration_validation.delete_validation"
    )
    pk_url_kwarg = "validation_id"
    success_url = reverse_lazy(
        "registration:validation_list"
    )
    http_method_names = [
        "post",
    ]

    def get_object(
        self,
        queryset=None,
    ):
        validation = super().get_object(
            queryset,
        )
        ensure_validation_editable(
            validation,
        )
        return validation

    def form_valid(
        self,
        form,
    ):
        now = timezone.now()
        self.object.deleted_at = now
        self.object.save(
            update_fields=[
                "deleted_at",
                "updated_at",
            ],
        )
        messages.success(
            self.request,
            "Validación eliminada correctamente.",
        )
        return HttpResponseRedirect(
            self.get_success_url(),
        )


# ---------------------------------------------------------
# Servicios: catálogo general
# ---------------------------------------------------------

def scoped_services():
    """Retorna los servicios que no están archivados."""
    return Service.objects.filter(deleted_at__isnull=True)


def filtered_services(request):
    """Permite buscar y filtrar servicios."""
    services = scoped_services()

    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()

    if query:
        services = services.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(description__icontains=query)
        )

    if selected_status == "active":
        services = services.filter(status=True)

    elif selected_status == "inactive":
        services = services.filter(status=False)

    return services.order_by("name", "service_id")


def service_metrics():
    """Calcula los indicadores del mantenedor."""
    services = scoped_services()

    return {
        "total_services": services.count(),
        "active_services": services.filter(
            status=True
        ).count(),
        "inactive_services": services.filter(
            status=False
        ).count(),
    }


class ServicePermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    """Controla el acceso mediante permisos Django."""

    login_url = "login"
    raise_exception = True

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(
                "No tienes permisos para realizar esta operación."
            )

        return redirect_to_login(
            self.request.get_full_path(),
            self.get_login_url(),
            self.get_redirect_field_name(),
        )


class ServiceScopeMixin:
    """Impide editar o eliminar servicios archivados."""

    def get_queryset(self):
        return scoped_services()


class ServiceFormMixin:
    """Entrega el usuario actual al formulario."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class ServicePageContextMixin:
    """Prepara el contexto para los formularios modales."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["services"] = filtered_services(self.request)

        context["query"] = self.request.GET.get(
            "q", ""
        ).strip()

        context["selected_status"] = self.request.GET.get(
            "status", ""
        ).strip()

        context.update(service_metrics())

        context.update(
            registration_page_size_context(self.request)
        )

        context["open_modal"] = True

        return context


# ---------------------------------------------------------
# READ: Listar y buscar servicios
# ---------------------------------------------------------

class ServiceListView(
    ServicePermissionMixin,
    RegistrationPaginationMixin,
    ListView,
):
    model = Service

    permission_required = (
        "registration_validation.view_service"
    )

    template_name = (
        "registration_validation/service_list.html"
    )

    context_object_name = "services"

    def get_queryset(self):
        return filtered_services(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["query"] = self.request.GET.get(
            "q", ""
        ).strip()

        context["selected_status"] = self.request.GET.get(
            "status", ""
        ).strip()

        context.update(service_metrics())

        return context


# ---------------------------------------------------------
# CREATE: Crear servicios
# ---------------------------------------------------------

class ServiceCreateView(
    ServicePermissionMixin,
    ServiceFormMixin,
    ServicePageContextMixin,
    CreateView,
):
    model = Service

    form_class = ServiceForm

    permission_required = (
        "registration_validation.add_service"
    )

    template_name = (
        "registration_validation/service_list.html"
    )

    success_url = reverse_lazy(
        "registration:service_list"
    )

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.success(
            self.request,
            "Servicio creado correctamente.",
        )

        return response


# ---------------------------------------------------------
# UPDATE: Modificar servicios
# ---------------------------------------------------------

class ServiceUpdateView(
    ServicePermissionMixin,
    ServiceScopeMixin,
    ServiceFormMixin,
    ServicePageContextMixin,
    UpdateView,
):
    model = Service

    form_class = ServiceForm

    permission_required = (
        "registration_validation.change_service"
    )

    template_name = (
        "registration_validation/service_list.html"
    )

    pk_url_kwarg = "service_id"

    success_url = reverse_lazy(
        "registration:service_list"
    )

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.success(
            self.request,
            "Servicio actualizado correctamente.",
        )

        return response


# ---------------------------------------------------------
# DELETE: Eliminación lógica
# ---------------------------------------------------------

class ServiceDeleteView(
    ServicePermissionMixin,
    ServiceScopeMixin,
    DeleteView,
):
    model = Service

    permission_required = (
        "registration_validation.delete_service"
    )

    pk_url_kwarg = "service_id"

    success_url = reverse_lazy(
        "registration:service_list"
    )

    # Solo permite eliminar mediante POST.
    http_method_names = ["post"]

    def form_valid(self, form):
        self.object.deleted_at = timezone.now()

        self.object.save(
            update_fields=["deleted_at", "updated_at"]
        )

        messages.success(
            self.request,
            "Servicio archivado correctamente.",
        )

        return HttpResponseRedirect(
            self.get_success_url()
        )

# ---------------------------------------------------------
# Tipo de Actividad: catálogo general
# ---------------------------------------------------------

def scoped_activity_types():
    return ActivityType.objects.filter(
        deleted_at__isnull=True
    )


def filtered_activity_types(request):
    types = scoped_activity_types()

    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get(
        "status", ""
    ).strip()

    if query:
        types = types.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(description__icontains=query)
        )

    if selected_status == "active":
        types = types.filter(status=True)

    elif selected_status == "inactive":
        types = types.filter(status=False)

    return types.order_by(
        "name",
        "activity_type_id",
    )


def activity_type_metrics():
    types = scoped_activity_types()

    return {
        "total_activity_types": types.count(),
        "active_activity_types": types.filter(
            status=True
        ).count(),
        "inactive_activity_types": types.filter(
            status=False
        ).count(),
    }


class ActivityTypePermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    login_url = "login"
    raise_exception = True

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(
                "No tienes permisos para realizar esta operación."
            )

        return redirect_to_login(
            self.request.get_full_path(),
            self.get_login_url(),
            self.get_redirect_field_name(),
        )


class ActivityTypeScopeMixin:

    def get_queryset(self):
        return scoped_activity_types()


class ActivityTypeFormMixin:

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class ActivityTypePageContextMixin:

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["activity_types"] = (
            filtered_activity_types(self.request)
        )

        context["query"] = self.request.GET.get(
            "q", ""
        ).strip()

        context["selected_status"] = self.request.GET.get(
            "status", ""
        ).strip()

        context.update(activity_type_metrics())
        context.update(
            registration_page_size_context(self.request)
        )

        context["open_modal"] = True

        return context


class ActivityTypeListView(
    ActivityTypePermissionMixin,
    RegistrationPaginationMixin,
    ListView,
):
    model = ActivityType

    permission_required = (
        "registration_validation.view_activitytype"
    )

    template_name = (
        "registration_validation/activity_type_list.html"
    )

    context_object_name = "activity_types"

    def get_queryset(self):
        return filtered_activity_types(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["query"] = self.request.GET.get(
            "q", ""
        ).strip()

        context["selected_status"] = self.request.GET.get(
            "status", ""
        ).strip()

        context.update(activity_type_metrics())

        return context


class ActivityTypeCreateView(
    ActivityTypePermissionMixin,
    ActivityTypeFormMixin,
    ActivityTypePageContextMixin,
    CreateView,
):
    model = ActivityType
    form_class = ActivityTypeForm

    permission_required = (
        "registration_validation.add_activitytype"
    )

    template_name = (
        "registration_validation/activity_type_list.html"
    )

    success_url = reverse_lazy(
        "registration:activity_type_list"
    )

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.success(
            self.request,
            "Tipo de actividad creado correctamente.",
        )

        return response


class ActivityTypeUpdateView(
    ActivityTypePermissionMixin,
    ActivityTypeScopeMixin,
    ActivityTypeFormMixin,
    ActivityTypePageContextMixin,
    UpdateView,
):
    model = ActivityType
    form_class = ActivityTypeForm

    permission_required = (
        "registration_validation.change_activitytype"
    )

    template_name = (
        "registration_validation/activity_type_list.html"
    )

    pk_url_kwarg = "activity_type_id"

    success_url = reverse_lazy(
        "registration:activity_type_list"
    )

    def form_valid(self, form):
        response = super().form_valid(form)

        messages.success(
            self.request,
            "Tipo de actividad actualizado correctamente.",
        )

        return response


class ActivityTypeDeleteView(
    ActivityTypePermissionMixin,
    ActivityTypeScopeMixin,
    DeleteView,
):
    model = ActivityType

    permission_required = (
        "registration_validation.delete_activitytype"
    )

    pk_url_kwarg = "activity_type_id"

    success_url = reverse_lazy(
        "registration:activity_type_list"
    )

    http_method_names = ["post"]

    def form_valid(self, form):
        self.object.deleted_at = timezone.now()

        self.object.save(
            update_fields=["deleted_at", "updated_at"]
        )

        messages.success(
            self.request,
            "Tipo de actividad archivado correctamente.",
        )

        return HttpResponseRedirect(
            self.get_success_url()
        )

# ---------------------------------------------------------
# Tipo de Atención: catálogo general
# ---------------------------------------------------------


def scoped_attention_types():
    """Retorna tipos no archivados; el acceso se controla con permisos."""
    return AttentionType.objects.filter(deleted_at__isnull=True)


def filtered_attention_types(request):
    """Búsqueda por código, nombre o descripción y filtro de estado."""
    types = scoped_attention_types()
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()

    if query:
        types = types.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(description__icontains=query)
        )

    if selected_status == "active":
        types = types.filter(status=True)
    elif selected_status == "inactive":
        types = types.filter(status=False)

    return types.order_by("name", "attention_type_id")


def attention_type_metrics():
    types = scoped_attention_types()
    return {
        "total_attention_types": types.count(),
        "active_attention_types": types.filter(status=True).count(),
        "inactive_attention_types": types.filter(status=False).count(),
    }


class AttentionTypePermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    """Protege cada operación mediante permisos Django específicos."""
    login_url = "login"
    raise_exception = True

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(
                "No tienes permisos para realizar esta operación."
            )
        return redirect_to_login(
            self.request.get_full_path(),
            self.get_login_url(),
            self.get_redirect_field_name(),
        )


class AttentionTypeScopeMixin:
    """Evita modificar o eliminar tipos archivados."""

    def get_queryset(self):
        return scoped_attention_types()


class AttentionTypeFormMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class AttentionTypePageContextMixin:
    """Presenta errores del formulario en el modal, junto al listado."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attention_types"] = filtered_attention_types(self.request)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_status"] = self.request.GET.get(
            "status", ""
        ).strip()
        context.update(attention_type_metrics())
        context.update(registration_page_size_context(self.request))
        context["open_modal"] = True
        return context


class AttentionTypeListView(
    AttentionTypePermissionMixin,
    RegistrationPaginationMixin,
    ListView,
):
    model = AttentionType
    permission_required = "registration_validation.view_attentiontype"
    template_name = "registration_validation/attention_type_list.html"
    context_object_name = "attention_types"

    def get_queryset(self):
        return filtered_attention_types(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_status"] = self.request.GET.get(
            "status", ""
        ).strip()
        context.update(attention_type_metrics())
        return context


class AttentionTypeCreateView(
    AttentionTypePermissionMixin,
    AttentionTypeFormMixin,
    AttentionTypePageContextMixin,
    CreateView,
):
    model = AttentionType
    form_class = AttentionTypeForm
    permission_required = "registration_validation.add_attentiontype"
    template_name = "registration_validation/attention_type_list.html"
    success_url = reverse_lazy("registration:attention_type_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Tipo de atención creado correctamente.")
        return response


class AttentionTypeUpdateView(
    AttentionTypePermissionMixin,
    AttentionTypeScopeMixin,
    AttentionTypeFormMixin,
    AttentionTypePageContextMixin,
    UpdateView,
):
    model = AttentionType
    form_class = AttentionTypeForm
    permission_required = "registration_validation.change_attentiontype"
    template_name = "registration_validation/attention_type_list.html"
    pk_url_kwarg = "attention_type_id"
    success_url = reverse_lazy("registration:attention_type_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Tipo de atención actualizado correctamente.",
        )
        return response


class AttentionTypeDeleteView(
    AttentionTypePermissionMixin,
    AttentionTypeScopeMixin,
    DeleteView,
):
    model = AttentionType
    permission_required = "registration_validation.delete_attentiontype"
    pk_url_kwarg = "attention_type_id"
    success_url = reverse_lazy("registration:attention_type_list")
    http_method_names = ["post"]

    def form_valid(self, form):
        # No archivamos un tipo que ya se usa en subatenciones
        # o ingresos. Así conservamos la integridad del catálogo.
        has_subattentions = SubAttention.objects.filter(
            attention_type=self.object
        ).exists()
        has_entries = AttentionEntry.objects.filter(
            attention_type=self.object
        ).exists()

        if has_subattentions or has_entries:
            messages.error(
                self.request,
                "No se puede eliminar este tipo de atención porque "
                "tiene subatenciones o ingresos asociados. "
                "Puedes cambiar su estado a Inactivo.",
            )
            return HttpResponseRedirect(self.get_success_url())

        self.object.deleted_at = timezone.now()
        self.object.save(update_fields=["deleted_at", "updated_at"])
        messages.success(
            self.request,
            "Tipo de atención eliminado correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())

# ---------------------------------------------------------
# Sub Atención: catálogo de subatenciones
# ---------------------------------------------------------


def scoped_sub_attentions():
    """Retorna únicamente subatenciones que no están eliminadas."""
    return (
        SubAttention.objects
        .filter(deleted_at__isnull=True)
        .select_related("attention_type")
    )


def filtered_sub_attentions(request):
    """Aplica búsqueda y filtro de estado al catálogo."""
    sub_attentions = scoped_sub_attentions()
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()

    if query:
        sub_attentions = sub_attentions.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(attention_type__code__icontains=query)
            | Q(attention_type__name__icontains=query)
        )

    if selected_status == "active":
        sub_attentions = sub_attentions.filter(status=True)
    elif selected_status == "inactive":
        sub_attentions = sub_attentions.filter(status=False)

    selected_type = request.GET.get("attention_type", "").strip()
    if selected_type.isdecimal():
        sub_attentions = sub_attentions.filter(attention_type_id=selected_type)

    return sub_attentions.order_by("name", "sub_attention_id")


def sub_attention_metrics():
    """Contadores generales, sin incluir registros eliminados."""
    sub_attentions = scoped_sub_attentions()
    return {
        "total_sub_attentions": sub_attentions.count(),
        "active_sub_attentions": sub_attentions.filter(status=True).count(),
        "inactive_sub_attentions": sub_attentions.filter(status=False).count(),
    }


class SubAttentionPermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    """Exige el permiso correspondiente a cada operación CRUD."""

    login_url = "login"
    raise_exception = True

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(
                "No tienes permisos para realizar esta operación."
            )
        return redirect_to_login(
            self.request.get_full_path(),
            self.get_login_url(),
            self.get_redirect_field_name(),
        )


class SubAttentionScopeMixin:
    """Impide editar o eliminar una subatención archivada."""

    def get_queryset(self):
        return scoped_sub_attentions()


class SubAttentionFormMixin:
    """Mantiene el contrato de formularios que reciben request.user."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class SubAttentionPageContextMixin:
    """Reutiliza el listado al mostrar el modal de crear o editar."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sub_attentions"] = filtered_sub_attentions(self.request)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_status"] = self.request.GET.get(
            "status", ""
        ).strip()
        context["selected_type"] = self.request.GET.get("attention_type", "")
        context["attention_type_options"] = scoped_attention_types().order_by("name")
        context.update(sub_attention_metrics())
        context.update(registration_page_size_context(self.request))
        context["open_modal"] = True
        return context


class SubAttentionListView(
    SubAttentionPermissionMixin,
    RegistrationPaginationMixin,
    ListView,
):
    model = SubAttention
    permission_required = "registration_validation.view_subattention"
    template_name = "registration_validation/sub_attention_list.html"
    context_object_name = "sub_attentions"

    def get_queryset(self):
        return filtered_sub_attentions(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_status"] = self.request.GET.get(
            "status", ""
        ).strip()
        context["selected_type"] = self.request.GET.get("attention_type", "")
        context["attention_type_options"] = scoped_attention_types().order_by("name")
        context.update(sub_attention_metrics())
        return context


class SubAttentionCreateView(
    SubAttentionPermissionMixin,
    SubAttentionFormMixin,
    SubAttentionPageContextMixin,
    CreateView,
):
    model = SubAttention
    form_class = SubAttentionForm
    permission_required = "registration_validation.add_subattention"
    template_name = "registration_validation/sub_attention_list.html"
    success_url = reverse_lazy("registration:sub_attention_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Subatención creada correctamente.",
        )
        return response


class SubAttentionUpdateView(
    SubAttentionPermissionMixin,
    SubAttentionScopeMixin,
    SubAttentionFormMixin,
    SubAttentionPageContextMixin,
    UpdateView,
):
    model = SubAttention
    form_class = SubAttentionForm
    permission_required = "registration_validation.change_subattention"
    template_name = "registration_validation/sub_attention_list.html"
    pk_url_kwarg = "sub_attention_id"
    success_url = reverse_lazy("registration:sub_attention_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Subatención actualizada correctamente.",
        )
        return response


class SubAttentionDeleteView(
    SubAttentionPermissionMixin,
    SubAttentionScopeMixin,
    DeleteView,
):
    model = SubAttention
    permission_required = "registration_validation.delete_subattention"
    pk_url_kwarg = "sub_attention_id"
    success_url = reverse_lazy("registration:sub_attention_list")
    http_method_names = ["post"]

    def form_valid(self, form):
        # Protegemos referencias históricas, incluso si el ingreso
        # asociado fue eliminado lógicamente.
        has_entries = AttentionEntry.objects.filter(
            sub_attention=self.object
        ).exists()

        if has_entries:
            messages.error(
                self.request,
                "No se puede eliminar esta subatención porque "
                "tiene ingresos asociados. Puedes cambiar "
                "su estado a Inactivo.",
            )
            return HttpResponseRedirect(self.get_success_url())

        self.object.deleted_at = timezone.now()
        self.object.save(update_fields=["deleted_at", "updated_at"])
        messages.success(
            self.request,
            "Subatención eliminada correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())

# ---------------------------------------------------------
# Ingreso de Atención: solicitudes registradas
# ---------------------------------------------------------


def scoped_attention_entries(user, permission="registration_validation.view_attentionentry"):
    """Limita los ingresos visibles a la delegación del usuario.

    Los superusuarios pueden consultar todas las delegaciones.
    Los ingresos eliminados lógicamente nunca aparecen en el CRUD.
    """
    entries = (
        AttentionEntry.objects
        .filter(deleted_at__isnull=True)
        .select_related(
            "attention_type",
            "sub_attention",
            "delegation",
            "responsible_employee",
            "responsible_employee__delegation",
            "registered_by",
            "citizen_request",
            "citizen",
        )
    )

    if user.is_superuser:
        return entries

    allowed_ids = allowed_delegation_ids(user, permission)
    if not allowed_ids:
        return entries.none()
    return entries.filter(delegation_id__in=allowed_ids)


def filtered_attention_entries(request):
    """Aplica búsqueda y filtros, respetando siempre la delegación."""
    entries = scoped_attention_entries(request.user)
    query = request.GET.get("q", "").strip()
    selected_type = request.GET.get("attention_type", "").strip()
    selected_delegation = request.GET.get("delegation", "").strip()
    selected_status = request.GET.get("status", "active").strip()
    if selected_status == "closed":
        entries = entries.filter(status="CLOSED")
    elif selected_status != "all":
        entries = entries.exclude(status="CLOSED")

    if query:
        entries = entries.filter(
            Q(requester__icontains=query)
            | Q(description__icontains=query)
            | Q(attention_type__name__icontains=query)
            | Q(attention_type__code__icontains=query)
            | Q(sub_attention__name__icontains=query)
            | Q(sub_attention__code__icontains=query)
            | Q(responsible_employee__name__icontains=query)
            | Q(delegation__name__icontains=query)
        )

    if selected_type.isdecimal() and len(selected_type) <= 18:
        entries = entries.filter(attention_type_id=int(selected_type))

    if selected_delegation.isdecimal() and len(selected_delegation) <= 18:
        entries = entries.filter(delegation_id=int(selected_delegation))

    return entries.order_by("-registration_date", "-attention_entry_id")


def attention_entry_metrics(user):
    """Entrega indicadores calculados solamente sobre ingresos visibles."""
    entries = scoped_attention_entries(user)
    today = timezone.localdate()
    return {
        "total_attention_entries": entries.count(),
        "month_attention_entries": entries.filter(
            registration_date__year=today.year,
            registration_date__month=today.month,
        ).count(),
        "latest_attention_entry_date": (
            entries.order_by("-registration_date")
            .values_list("registration_date", flat=True)
            .first()
        ),
    }


def attention_entry_filter_context(request):
    """Opciones del listado que no amplían la visibilidad del usuario."""
    visible_entries = scoped_attention_entries(request.user)
    type_ids = visible_entries.values_list(
        "attention_type_id", flat=True
    ).distinct()
    delegation_ids = visible_entries.values_list(
        "delegation_id", flat=True
    ).distinct()

    return {
        "query": request.GET.get("q", "").strip(),
        "selected_attention_type": request.GET.get(
            "attention_type", ""
        ).strip(),
        "selected_delegation": request.GET.get(
            "delegation", ""
        ).strip(),
        "selected_status": request.GET.get("status", "active").strip(),
        "attention_type_options": (
            AttentionType.objects.filter(pk__in=type_ids)
            .order_by("name", "attention_type_id")
        ),
        "delegation_options": (
            Delegation.objects.filter(pk__in=delegation_ids)
            .order_by("name", "pk")
        ),
    }


@login_required
def attention_entry_detail(request, attention_entry_id):
    """Returns one scoped attention entry for the shared read-only modal."""
    attention_entry = get_object_or_404(
        scoped_attention_entries(
            request.user,
            "registration_validation.view_attentionentry",
        ),
        attention_entry_id=attention_entry_id,
    )
    citizen_request = getattr(attention_entry, "citizen_request", None)
    return JsonResponse(
        {
            "attention": {
                "id": attention_entry.pk,
                "tracking_code": (
                    str(attention_entry.tracking_code)
                    if attention_entry.tracking_code
                    else ""
                ),
                "request_tracking_code": (
                    str(citizen_request.tracking_code)
                    if citizen_request is not None
                    else ""
                ),
                "requester": (attention_entry.citizen.full_name if attention_entry.citizen_id else attention_entry.requester),
                "requester_email": (attention_entry.citizen.email if attention_entry.citizen_id else attention_entry.requester_email),
                "requester_phone": (attention_entry.citizen.phone if attention_entry.citizen_id else attention_entry.requester_phone),
                "address": (attention_entry.citizen.address if attention_entry.citizen_id else attention_entry.address),
                "subject": attention_entry.subject,
                "attention_type": attention_entry.attention_type.name,
                "sub_attention": attention_entry.sub_attention.name,
                "description": attention_entry.description,
                "delegation": attention_entry.delegation.name,
                "responsible_employee": (
                    attention_entry.responsible_employee.name
                    if attention_entry.responsible_employee_id
                    else ""
                ),
                "status": attention_entry.get_status_display(),
                "tracking_status": (
                    "Cerrada" if attention_entry.status == "CLOSED" else
                    "Resuelta" if attention_entry.status == "RESOLVED" else
                    "En gestión" if citizen_request else attention_entry.get_status_display()
                ),
                "registration_date": (
                    attention_entry.registration_date.isoformat()
                    if attention_entry.registration_date
                    else ""
                ),
                "registered_by": (
                    attention_entry.registered_by.username
                    if attention_entry.registered_by_id
                    else ""
                ),
            }
        }
    )


def _create_internal_request(attention, actor):
    """Vincular el ingreso manual al mismo seguimiento público, sin doble captura."""
    citizen_request = CitizenRequest.objects.create(
        citizen=attention.citizen,
        origin="INTERNAL",
        tracking_code=attention.tracking_code,
        requester_name=attention.requester,
        requester_email=attention.requester_email,
        requester_phone=attention.requester_phone,
        address=attention.address,
        subject=attention.subject,
        description=attention.description,
        delegation=attention.delegation,
        assigned_to=attention.responsible_employee,
        attention_entry=attention,
        status="CLOSED" if attention.status == "CLOSED" else "IN_PROGRESS",
    )
    for previous_status, new_status, observation in (
        ("", "NEW", "Solicitud ingresada manualmente por funcionario."),
        ("NEW", "NEW", f"Derivada a {attention.delegation.name}."),
        ("NEW", citizen_request.status, "Atención registrada; caso en gestión."),
    ):
        RequestEvent.objects.create(
            request=citizen_request, actor=actor, observation=observation,
            previous_status=previous_status, new_status=new_status,
        )
    return citizen_request


def _notify_attention_state(citizen_request, state_label, *, initial=False):
    # Captura de valores escalares: no se envían correos si se revierte la transacción.
    if not citizen_request.followup_recipient:
        return
    visible_stages = tuple(stage["label"] for stage in tracking_stages(citizen_request))
    transaction.on_commit(
        lambda request_id=citizen_request.pk,
        name=(citizen_request.citizen.full_name if citizen_request.citizen_id
              else citizen_request.requester_name),
        email=citizen_request.followup_recipient,
        code=str(citizen_request.tracking_code),
        label=state_label, is_initial=initial,
        stages=visible_stages: send_request_state_notification(
            request_id, name, email, code, label, initial=is_initial, stages=stages,
        )
    )


def _sync_request_status(attention, actor, previous_status, observation):
    """Propaga al seguimiento el cambio real, con evento y aviso por correo."""
    citizen_request = CitizenRequest.objects.select_for_update().filter(
        attention_entry=attention,
    ).first()
    if citizen_request is None:
        citizen_request = _create_internal_request(attention, actor)
        _notify_attention_state(citizen_request, "En gestión" if attention.status == "IN_PROGRESS" else attention.get_status_display(), initial=True)
        return
    old_request_status = citizen_request.status
    # No reemplazar los datos originales, tampoco en solicitudes manuales.
    # En particular, el correo original sigue siendo el destinatario verificado
    # hasta que exista un proceso autorizado de cambio de correo.
    citizen_request.status = "CLOSED" if attention.status == "CLOSED" else "IN_PROGRESS"
    citizen_request.save()

    transition_from = old_request_status
    # Cerrar desde "En gestión" significa confirmar la solución; si fue
    # "No procede", el cierre NO se marca falsamente como resuelto.
    if attention.status == "CLOSED" and previous_status not in ("Resuelta", "No procede"):
        RequestEvent.objects.create(
            request=citizen_request, actor=actor,
            observation=f"Resolución confirmada al cerrar la atención. {observation}",
            previous_status=transition_from, new_status="RESOLVED",
        )
        transition_from = "RESOLVED"

    RequestEvent.objects.create(
        request=citizen_request, actor=actor,
        observation=f"Estado de atención: {previous_status} → {attention.get_status_display()}. {observation}",
        previous_status=transition_from,
        new_status=(attention.status if attention.status in ("RESOLVED", "REJECTED", "CLOSED") else "IN_PROGRESS"),
    )
    label = "En gestión (reabierta)" if old_request_status == "CLOSED" and attention.status == "IN_PROGRESS" else (
        "En gestión" if attention.status == "IN_PROGRESS" else attention.get_status_display()
    )
    _notify_attention_state(citizen_request, label)



class AttentionEntryPermissionMixin(
    LoginRequiredMixin,
    PermissionRequiredMixin,
):
    """Exige los permisos de Django para el ingreso de atención."""

    login_url = "login"
    raise_exception = True

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(
                "No tienes permisos para realizar esta operación."
            )
        return redirect_to_login(
            self.request.get_full_path(),
            self.get_login_url(),
            self.get_redirect_field_name(),
        )


class AttentionEntryScopeMixin:
    """Protege las operaciones sobre ingresos ya existentes."""

    def get_queryset(self):
        return scoped_attention_entries(self.request.user, self.permission_required)


class AttentionEntryFormMixin:
    """Pasa el usuario autenticado al formulario para restringir opciones."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class AttentionEntryPageContextMixin:
    """Reutiliza el listado cuando se abre el formulario modal."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attention_entries"] = filtered_attention_entries(
            self.request
        )
        context.update(attention_entry_filter_context(self.request))
        context.update(attention_entry_metrics(self.request.user))
        context.update(registration_page_size_context(self.request))
        context["open_modal"] = True
        return context


class AttentionEntryListView(
    AttentionEntryPermissionMixin,
    RegistrationPaginationMixin,
    ListView,
):
    model = AttentionEntry
    permission_required = "registration_validation.view_attentionentry"
    template_name = "registration_validation/attention_entry_list.html"
    context_object_name = "attention_entries"

    def get_queryset(self):
        return filtered_attention_entries(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(attention_entry_filter_context(self.request))
        context.update(attention_entry_metrics(self.request.user))
        return context


class AttentionEntryCreateView(
    AttentionEntryPermissionMixin,
    AttentionEntryFormMixin,
    AttentionEntryPageContextMixin,
    CreateView,
):
    model = AttentionEntry
    form_class = AttentionEntryForm
    permission_required = "registration_validation.add_attentionentry"
    template_name = "registration_validation/attention_entry_list.html"
    success_url = reverse_lazy("registration:attention_entry_list")

    def get_citizen_request(self):
        request_id = (
            self.request.GET.get("citizen_request")
            or self.request.POST.get("citizen_request")
        )
        if not request_id:
            return None
        citizen_request = get_object_or_404(
            CitizenRequest.objects.select_related("delegation"),
            pk=request_id,
            delegation__isnull=False,
        )
        allowed_ids = allowed_delegation_ids(
            self.request.user,
            self.permission_required,
        )
        active_id = getattr(
            self.request.user,
            "sgr_active_delegation_id",
            None,
        )
        if (
            allowed_ids is not None
            and citizen_request.delegation_id not in allowed_ids
        ) or (
            not self.request.user.is_superuser
            and active_id != citizen_request.delegation_id
        ):
            raise PermissionDenied(
                "La solicitud no pertenece a tu delegación activa autorizada."
            )
        if citizen_request.attention_entry_id:
            raise PermissionDenied(
                "La solicitud ya tiene una atención vinculada."
            )
        return citizen_request

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        citizen_request = self.get_citizen_request()
        if citizen_request is not None:
            kwargs["instance"] = AttentionEntry(
                citizen=citizen_request.citizen,
                requester=citizen_request.requester_name,
                requester_email=citizen_request.requester_email,
                requester_phone=citizen_request.requester_phone,
                address=citizen_request.address,
                subject=citizen_request.subject,
                description=citizen_request.description,
                delegation=citizen_request.delegation,
            )
        if citizen_request is not None and citizen_request.citizen_id:
            kwargs.setdefault("initial", {})["citizen_rut"] = citizen_request.citizen.rut
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["citizen_request"] = self.get_citizen_request()
        context["citizen_form"] = CitizenForm()
        context["groups"] = Citizen.objects.exclude(neighborhood_group="").values_list("neighborhood_group", flat=True).distinct()
        return context

    def form_valid(self, form):
        citizen_request = self.get_citizen_request()
        rut = form.cleaned_data.get("citizen_rut")
        linked_citizen = Citizen.objects.filter(rut=rut, is_active=True).first() if rut else None
        if rut and linked_citizen is None:
            form.add_error("citizen_rut", "El RUT no está registrado como ciudadano activo.")
            return self.form_invalid(form)
        if linked_citizen and not self.request.user.has_perm("citizen_registry.view_citizen"):
            raise PermissionDenied("No tienes permiso para consultar ciudadanos.")
        if citizen_request is not None and citizen_request.citizen_id:
            if linked_citizen and citizen_request.citizen_id != linked_citizen.pk:
                form.add_error("citizen_rut", "La solicitud ya tiene otro ciudadano asociado.")
                return self.form_invalid(form)
            linked_citizen = citizen_request.citizen
        if linked_citizen:
            form.instance.citizen = linked_citizen
            form.instance.requester = linked_citizen.full_name
            form.instance.requester_email = linked_citizen.email
            form.instance.requester_phone = linked_citizen.phone
            form.instance.address = linked_citizen.address
        if citizen_request is None:
            with transaction.atomic():
                form.instance.origin = "INTERNAL"
                form.instance.status = "IN_PROGRESS"
                form.instance.registered_by = self.request.user
                self.object = form.save()
                citizen_request = _create_internal_request(self.object, self.request.user)
                _notify_attention_state(citizen_request, "En gestión", initial=True)
            messages.success(
                self.request,
                "Atención registrada. Se generó un código de seguimiento y "
                "se notificará al ciudadano si tiene correo electrónico.",
            )
            return HttpResponseRedirect(self.get_success_url())

        with transaction.atomic():
            citizen_request = get_object_or_404(
                CitizenRequest.objects.select_for_update().select_related(
                    "delegation",
                ),
                pk=citizen_request.pk,
                delegation__isnull=False,
            )
            if citizen_request.attention_entry_id:
                raise PermissionDenied(
                    "La solicitud ya tiene una atención vinculada."
                )
            active_id = getattr(
                self.request.user,
                "sgr_active_delegation_id",
                None,
            )
            allowed_ids = allowed_delegation_ids(
                self.request.user,
                self.permission_required,
            )
            if (
                allowed_ids is not None
                and citizen_request.delegation_id not in allowed_ids
            ) or (
                not self.request.user.is_superuser
                and active_id != citizen_request.delegation_id
            ):
                raise PermissionDenied(
                    "La solicitud ya no pertenece a tu delegación activa."
                )
            # Solicitud: conservar datos originales. Atención: usar siempre el
            # ciudadano elegido desde el CRUD, no los datos personales del POST.
            # El asunto y la descripción sí pueden corregirse en la atención.
            for field in ("subject", "description"):
                if field not in self.request.POST:
                    setattr(form.instance, field, getattr(citizen_request, field))
            if linked_citizen:
                form.instance.citizen = linked_citizen
                form.instance.requester = linked_citizen.full_name
                form.instance.requester_email = linked_citizen.email or citizen_request.requester_email
                form.instance.requester_phone = linked_citizen.phone
                form.instance.address = linked_citizen.address
            else:
                form.instance.requester = citizen_request.requester_name
                form.instance.requester_email = citizen_request.requester_email
                form.instance.requester_phone = citizen_request.requester_phone
                form.instance.address = citizen_request.address
            form.instance.origin = "CITIZEN"
            form.instance.delegation = citizen_request.delegation
            form.instance.tracking_code = citizen_request.tracking_code
            form.instance.status = "IN_PROGRESS"
            form.instance.registered_by = self.request.user
            self.object = form.save()
            citizen_request.attention_entry = self.object
            if linked_citizen:
                citizen_request.citizen = linked_citizen
            previous_request_status = citizen_request.status
            citizen_request.status = "IN_PROGRESS"
            citizen_request.save(
                update_fields=("attention_entry", "citizen", "status", "updated_at"),
            )
            corrected_fields = [
                name for name, original, updated in (
                    ("solicitante", citizen_request.requester_name, self.object.requester),
                    ("correo", citizen_request.requester_email, self.object.requester_email),
                    ("teléfono", citizen_request.requester_phone, self.object.requester_phone),
                    ("dirección", citizen_request.address, self.object.address),
                    ("asunto", citizen_request.subject, self.object.subject),
                    ("descripción", citizen_request.description, self.object.description),
                    ("RUT vinculado", citizen_request.citizen_id, self.object.citizen_id),
                    ("delegación", citizen_request.delegation_id, self.object.delegation_id),
                    ("responsable", citizen_request.assigned_to_id, self.object.responsible_employee_id),
                ) if original != updated
            ]
            detail = (
                " Se ajustaron los datos de la atención: "
                + ", ".join(corrected_fields) + ". La solicitud original se conserva."
                if corrected_fields else ""
            )
            RequestEvent.objects.create(
                request=citizen_request,
                actor=self.request.user,
                observation=(
                    "Atención creada desde solicitud. "
                    f"Identificador de atención: {self.object.pk}." + detail
                ),
                previous_status=previous_request_status,
                new_status=citizen_request.status,
            )
        messages.success(
            self.request,
            "Ingreso de atención registrado correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())


class AttentionEntryUpdateView(
    AttentionEntryPermissionMixin,
    AttentionEntryScopeMixin,
    AttentionEntryFormMixin,
    AttentionEntryPageContextMixin,
    UpdateView,
):
    model = AttentionEntry
    form_class = AttentionEntryForm
    permission_required = "registration_validation.change_attentionentry"
    template_name = "registration_validation/attention_entry_list.html"
    pk_url_kwarg = "attention_entry_id"
    success_url = reverse_lazy("registration:attention_entry_list")

    def get(self, request, *args, **kwargs):
        if self.get_object().status == "CLOSED":
            raise PermissionDenied("La atención está cerrada: solo puedes consultarla o reabrirla.")
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "resend_email_verification":
            with transaction.atomic():
                attention = get_object_or_404(
                    scoped_attention_entries(request.user, self.permission_required).select_for_update(),
                    pk=self.kwargs["attention_entry_id"],
                )
                linked = CitizenRequest.objects.select_for_update().filter(attention_entry=attention).first()
                if linked is None or not linked.followup_email_paused or not linked.citizen_id:
                    raise PermissionDenied("La atención no tiene una verificación de correo pendiente.")
                linked.citizen.refresh_from_db()
                reset_followup_email(linked, linked.citizen)
                linked.save(update_fields=["pending_followup_email","followup_email_paused","verified_followup_email","followup_verification_nonce","updated_at"])
                schedule_verification(linked)
            messages.success(request,"Verificación solicitada al correo actual del ciudadano, si está registrado.")
            return HttpResponseRedirect(reverse("registration:attention_entry_list"))
        if request.POST.get("action") == "reopen":
            with transaction.atomic():
                attention = get_object_or_404(
                    scoped_attention_entries(request.user, self.permission_required).select_for_update(),
                    pk=self.kwargs["attention_entry_id"],
                )
                if attention.status != "CLOSED":
                    raise PermissionDenied("Solo pueden reabrirse las atenciones cerradas.")
                previous = attention.get_status_display()
                attention.status = "IN_PROGRESS"
                attention.closed_at = None
                attention.save(update_fields=["status", "closed_at", "updated_at"])
                _sync_request_status(attention, request.user, previous, "Reapertura autorizada.")
            messages.success(request, "Atención reabierta y ciudadano notificado si tiene correo.")
            return HttpResponseRedirect(reverse("registration:attention_entry_list"))
        if self.get_object().status == "CLOSED":
            raise PermissionDenied("La atención cerrada no admite modificaciones.")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            previous = get_object_or_404(
                scoped_attention_entries(self.request.user, self.permission_required).select_for_update(),
                pk=self.object.pk,
            )
            if previous.status == "CLOSED":
                raise PermissionDenied("La atención ya fue cerrada.")
            old_status = previous.status
            if old_status != form.initial.get("status", old_status):
                raise PermissionDenied("El estado cambió mientras se editaba. Vuelve a abrir la atención.")
            self.object = form.save(commit=False)
            # El RUT es una vinculación, no un campo de texto. Solo puede
            # cambiarse a un ciudadano activo y existente con permiso de consulta.
            rut = form.cleaned_data.get("citizen_rut")
            citizen_changed = False
            linked_request = CitizenRequest.objects.select_for_update().filter(attention_entry=previous).first()
            if rut and (previous.citizen is None or rut != previous.citizen.rut):
                if not self.request.user.has_perm("citizen_registry.view_citizen"):
                    raise PermissionDenied("No tienes permiso para consultar ciudadanos.")
                citizen = Citizen.objects.filter(rut=rut, is_active=True).first()
                if citizen is None:
                    form.add_error("citizen_rut", "El RUT no está registrado como ciudadano activo.")
                    return self.form_invalid(form)
                if linked_request is None:
                    form.add_error("citizen_rut", "La atención debe tener una solicitud vinculada para corregir el ciudadano.")
                    return self.form_invalid(form)
                if not form.cleaned_data.get("confirm_citizen_change"):
                    form.add_error("citizen_rut", "Confirma el cambio de ciudadano antes de guardar.")
                    return self.form_invalid(form)
                citizen_changed = True
                self.object.citizen = citizen
            current_citizen = self.object.citizen if self.object.citizen_id else None
            if current_citizen is not None:
                self.object.requester = current_citizen.full_name
                self.object.requester_email = (
                    current_citizen.email or previous.requester_email
                    if previous.origin == "CITIZEN" else current_citizen.email
                )
                self.object.requester_phone = current_citizen.phone
                self.object.address = current_citizen.address
            else:
                for field in ("requester", "requester_email", "requester_phone", "address"):
                    setattr(self.object, field, getattr(previous, field))
            changed_details = [
                label for label, before, after in (
                    ("solicitante", previous.requester, self.object.requester),
                    ("correo", previous.requester_email, self.object.requester_email),
                    ("teléfono", previous.requester_phone, self.object.requester_phone),
                    ("dirección", previous.address, self.object.address),
                    ("asunto", previous.subject, self.object.subject),
                    ("descripción", previous.description, self.object.description),
                    ("RUT vinculado", previous.citizen_id, self.object.citizen_id),
                    ("tipo de atención", previous.attention_type_id, self.object.attention_type_id),
                    ("subatención", previous.sub_attention_id, self.object.sub_attention_id),
                    ("delegación", previous.delegation_id, self.object.delegation_id),
                    ("responsable", previous.responsible_employee_id, self.object.responsible_employee_id),
                ) if before != after
            ]
            if self.object.status != old_status:
                self.object.closed_at = timezone.now() if self.object.status == "CLOSED" else None
            self.object.save()
            form.save_m2m()
            if citizen_changed:
                # Corregir EL MISMO CASO: solicitud y atención apuntan al nuevo
                # ciudadano; la ficha original queda en sus snapshots y auditoría.
                old_citizen = previous.citizen or linked_request.citizen
                if linked_request.original_citizen_id is None and linked_request.citizen_id:
                    linked_request.original_citizen_id = linked_request.citizen_id
                linked_request.citizen = self.object.citizen
                reset_followup_email(linked_request, self.object.citizen)
                linked_request.save(update_fields=["citizen","original_citizen","pending_followup_email","verified_followup_email","followup_verification_nonce","followup_email_paused","updated_at"])
                RequestEvent.objects.create(
                    request=linked_request, actor=self.request.user,
                    observation=(
                        "Corrección de RUT confirmada por funcionario. "
                        f"Anterior: {old_citizen.rut if old_citizen else 'Sin RUT'} "
                        f"({old_citizen.full_name if old_citizen else 'Sin ciudadano'}). "
                        f"Nuevo: {self.object.citizen.rut} ({self.object.citizen.full_name}). "
                        "Notificaciones suspendidas hasta verificar el nuevo correo."
                    ),
                    previous_status=linked_request.status,new_status=linked_request.status,
                )
                schedule_verification(linked_request)
            if changed_details:
                linked_request = CitizenRequest.objects.select_for_update().filter(
                    attention_entry=self.object,
                ).first()
                if linked_request is not None:
                    RequestEvent.objects.create(
                        request=linked_request,
                        actor=self.request.user,
                        observation=(
                            "Datos de atención actualizados: "
                            + ", ".join(changed_details) + "."
                        ),
                        previous_status=linked_request.status,
                        new_status=linked_request.status,
                    )
            if self.object.status != old_status:
                old_label = previous.get_status_display()
                observation = (form.cleaned_data.get("closing_observation") or "").strip()
                _sync_request_status(self.object, self.request.user, old_label, observation)
        messages.success(self.request, "Ingreso de atención actualizado correctamente.")
        return HttpResponseRedirect(self.get_success_url())


class AttentionEntryDeleteView(
    AttentionEntryPermissionMixin,
    AttentionEntryScopeMixin,
    DeleteView,
):
    model = AttentionEntry
    permission_required = "registration_validation.delete_attentionentry"
    pk_url_kwarg = "attention_entry_id"
    success_url = reverse_lazy("registration:attention_entry_list")
    http_method_names = ["post"]

    def form_valid(self, form):
        # La comprobación también se realiza en el servidor y sobre el estado
        # más reciente, para impedir borrar una atención reabierta.
        with transaction.atomic():
            attention = get_object_or_404(
                self.get_queryset().select_for_update(), pk=self.object.pk,
            )
            if attention.status != "CLOSED":
                raise PermissionDenied("Primero debes cerrar la atención para poder eliminarla.")
            # Archivo lógico: no se borra la solicitud ni su historial.
            attention.deleted_at = timezone.now()
            attention.save(update_fields=["deleted_at", "updated_at"])
        messages.success(
            self.request,
            "Ingreso de atención eliminado correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())



@login_required
@permission_required("registration_validation.view_attentiontype", raise_exception=True)
def attention_type_export(request):
    """Exporta exactamente los filtros aplicados al catálogo."""
    return workbook_response("tipos_atencion.xlsx", ["Código", "Nombre", "Descripción", "Estado"], [
        (obj.code, obj.name, obj.description, "Activo" if obj.status else "Inactivo")
        for obj in filtered_attention_types(request)
    ])


@login_required
@permission_required("registration_validation.view_subattention", raise_exception=True)
def sub_attention_export(request):
    return workbook_response("subatenciones.xlsx", ["Código", "Nombre", "Tipo de atención", "Estado"], [
        (obj.code, obj.name, obj.attention_type.name, "Activo" if obj.status else "Inactivo")
        for obj in filtered_sub_attentions(request).select_related("attention_type")
    ])
