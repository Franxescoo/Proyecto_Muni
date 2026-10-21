from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
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


def scoped_validations(user):
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
    profile = getattr(
        user,
        "profile",
        None,
    )
    if (
        profile is None
        or profile.delegation_id is None
    ):
        return validations.none()
    return validations.filter(
        evidence__activity__author__delegation_id=(
            profile.delegation_id
        ),
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
            self.request.user,
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


def scoped_attention_entries(user):
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
        )
    )

    if user.is_superuser:
        return entries

    profile = getattr(user, "profile", None)
    delegation_id = (
        profile.delegation_id if profile is not None else None
    )

    if delegation_id is None:
        return entries.none()

    return entries.filter(delegation_id=delegation_id)


def filtered_attention_entries(request):
    """Aplica búsqueda y filtros, respetando siempre la delegación."""
    entries = scoped_attention_entries(request.user)
    query = request.GET.get("q", "").strip()
    selected_type = request.GET.get("attention_type", "").strip()
    selected_delegation = request.GET.get("delegation", "").strip()

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
        "attention_type_options": (
            AttentionType.objects.filter(pk__in=type_ids)
            .order_by("name", "attention_type_id")
        ),
        "delegation_options": (
            Delegation.objects.filter(pk__in=delegation_ids)
            .order_by("name", "pk")
        ),
    }


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
        return scoped_attention_entries(self.request.user)


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

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Ingreso de atención registrado correctamente.",
        )
        return response


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

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Ingreso de atención actualizado correctamente.",
        )
        return response


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
        # La eliminación es lógica: se conserva el historial y
        # las relaciones con el catálogo de tipos y subatenciones.
        self.object.deleted_at = timezone.now()
        self.object.save(update_fields=["deleted_at", "updated_at"])
        messages.success(
            self.request,
            "Ingreso de atención eliminado correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())

