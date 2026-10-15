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
from planning_measurements.models import Period
from .forms import (
    ActivityForm,
    EvidenceForm,
    ValidationForm,
)
from .models import (
    Activity,
    Evidence,
    EvidenceFile,
    Validation,
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
