from django import forms
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import transaction

from accounts.forms import (
    BootstrapMixin,
    EmployeeForm as AccountsEmployeeForm,
    PositionForm as AccountsPositionForm,
)

from .models import Delegation, OrganizationRole, PositionFunction, Employee
from accounts.models import UserProfile
from accounts.permissions import allowed_delegation_ids
from .permission_labels import SpanishPermissionMultipleChoiceField

STATUS_CHOICES = (
    ("", "Selecciona un estado"),
    ("Active", "Activo"),
    ("Inactive", "Inactivo"),
)


def _configure_status_choices(form):
    choices = list(STATUS_CHOICES)
    current_status = getattr(form.instance, "status", "")
    if current_status and current_status not in dict(choices):
        choices.append((current_status, current_status))
    form.fields["status"].choices = choices


def mark_invalid_fields(form):
    for field_name in form.errors:
        field = form.fields.get(field_name)
        if field is None:
            continue
        classes = field.widget.attrs.get("class", "").split()
        if "is-invalid" not in classes:
            classes.append("is-invalid")
        field.widget.attrs["class"] = " ".join(classes)


class OrganizationRoleForm(BootstrapMixin, forms.Form):
    name = forms.CharField(
        label="Nombre del rol",
        max_length=150,
        min_length=3,
    )
    description = forms.CharField(
        label="Descripción", widget=forms.Textarea(attrs={"rows": 2}),
        required=True, max_length=1000,
    )
    delegations = forms.ModelMultipleChoiceField(
        label="Delegaciones de aplicación",
        queryset=Delegation.objects.filter(
            deleted_at__isnull=True
        ).order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    permissions = SpanishPermissionMultipleChoiceField(
        label="Permisos",
        queryset=Permission.objects.filter(
            content_type__app_label__in=[
                "organization",
                "accounts",
                "planning_measurements",
                "registration_validation",
                "monitoring_traceability",
            ],
        ).select_related("content_type").order_by(
            "content_type__app_label",
            "content_type__model",
            "codename",
        ),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Selecciona las acciones permitidas para este rol.",
    )

    def __init__(self, *args, **kwargs):
        self.group = kwargs.pop("group", None)
        self.actor = kwargs.pop("actor", None)

        initial = dict(kwargs.pop("initial", {}))

        if self.group:
            initial.setdefault("name", self.group.name)
            initial.setdefault("permissions", self.group.permissions.all())

            role = OrganizationRole.objects.filter(
                group=self.group
            ).prefetch_related("application_delegations").first()

            if role:
                initial.setdefault("description", role.description)
                initial.setdefault(
                    "delegations",
                    role.application_delegations.values_list("pk", flat=True),
                )

        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

        self._preserved_permission_ids = set()

        if self.actor is not None and not self.actor.is_superuser:
            owned = self.actor.get_all_permissions()

            if self.group:
                self._preserved_permission_ids = {
                    p.pk
                    for p in self.group.permissions.select_related("content_type")
                    if f"{p.content_type.app_label}.{p.codename}" not in owned
                }

            permitted = [
                (name.split(".", 1)[0], name.split(".", 1)[1])
                for name in owned
            ]

            from django.db.models import Q
            from functools import reduce
            from operator import or_

            lookup = [
                Q(content_type__app_label=app, codename=code)
                for app, code in permitted
            ]

            self.fields["permissions"].queryset = (
                self.fields["permissions"].queryset.filter(
                    reduce(or_, lookup)
                )
                if lookup
                else self.fields["permissions"].queryset.none()
            )

            scopes = allowed_delegation_ids(
                self.actor,
                "organization.change_organizationrole"
                if self.group
                else "organization.add_organizationrole",
                active_only=False,
            )

            self.fields["delegations"].queryset = (
                self.fields["delegations"].queryset.filter(pk__in=scopes)
            )

            if self._preserved_permission_ids:
                self.fields["delegations"].disabled = True

                self.fields["delegations"].help_text = (
                    "Las delegaciones quedan bloqueadas porque este rol "
                    "tiene permisos que no puedes administrar."
                )

                self.fields["permissions"].help_text = (
                    "Puedes modificar los permisos que posees. "
                    "Los demás se conservarán sin cambios."
                )

        self.apply_bootstrap()

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicate = Group.objects.filter(name__iexact=name)
        if self.group:
            duplicate = duplicate.exclude(pk=self.group.pk)
        if duplicate.exists():
            raise ValidationError("Ya existe un rol con ese nombre.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        delegations = cleaned_data.get("delegations")
        if not delegations:
            self.add_error(
                "delegations",
                "Selecciona al menos una delegación de aplicación.",
            )
        return cleaned_data

    def save(self):
        with transaction.atomic():
            group = self.group or Group()
            group.name = self.cleaned_data["name"]
            group.save()
            selected = {
                p.pk for p in self.cleaned_data["permissions"]
            }

            group.permissions.set(
                selected | self._preserved_permission_ids
            )
            role, _ = OrganizationRole.objects.update_or_create(
                group=group,
                defaults={"delegation": self.cleaned_data["delegations"].first()},
            )
            role.description = self.cleaned_data["description"].strip()
            role.save(update_fields=["description"])
            role.application_delegations.set(self.cleaned_data["delegations"])
        return group


class DelegationForm(BootstrapMixin, forms.ModelForm):
    status = forms.ChoiceField(choices=STATUS_CHOICES, label="Estado")

    class Meta:
        model = Delegation
        fields = ["code", "name", "address", "commune", "scope", "responsible", "status"]
        labels = {
            "code": "Código", "name": "Nombre de la delegación",
            "address": "Dirección", "commune": "Comuna", "scope": "Ámbito",
            "responsible": "Responsable de delegación", "status": "Estado",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ej. Delegación Centro"}),
            "scope": forms.TextInput(attrs={"placeholder": "Ej. Urbano o rural"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = True
        self.fields["address"].required = True
        self.fields["commune"].required = True
        from .models import Employee
        employees = Employee.objects.filter(deleted_at__isnull=True, status__iexact="Active")
        if self.instance.pk:
            employees = employees.filter(delegation=self.instance)
            if self.instance.responsible_id:
                employees = Employee.objects.filter(
                    Q(pk=self.instance.responsible_id) | Q(pk__in=employees.values("pk"))
                )
        else:
            employees = employees.none()  # No existe delegación aún: asignar responsable después.
            self.fields["responsible"].help_text = (
                "Guarda primero la delegación y luego asigna su responsable al editarla."
            )
        self.fields["responsible"].queryset = employees.order_by("name")
        self.apply_bootstrap()
        _configure_status_choices(self)

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        qs = Delegation.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("El código ya está registrado.")
        return code

    def clean(self):
        data = super().clean()
        responsible = data.get("responsible")
        if responsible and (
            not self.instance.pk or responsible.delegation_id != self.instance.pk
        ):
            self.add_error("responsible", "El responsable debe pertenecer a esta delegación.")
        return data

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if len(name) < 3:
            raise ValidationError(
                "El nombre debe tener al menos 3 caracteres."
            )
        duplicates = Delegation.objects.filter(
            name__iexact=name,
            deleted_at__isnull=True,
        )
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError(
                "Ya existe una delegación activa con ese nombre."
            )
        return name

    def clean_scope(self):
        scope = self.cleaned_data["scope"].strip()
        if len(scope) < 2:
            raise ValidationError(
                "El ámbito debe tener al menos 2 caracteres."
            )
        return scope

class AccountRolePreviewSelect(forms.Select):
    def create_option(
        self, name, value, label, selected,
        index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected,
            index, subindex, attrs
        )

        if value and hasattr(value, "instance"):
            profile = value.instance

            option["attrs"]["data-roles"] = ", ".join(
                group.name
                for group in profile.user.groups.all()
            )

            option["attrs"]["data-delegation"] = str(
                profile.delegation_id or ""
            )

        return option


class EmployeeForm(AccountsEmployeeForm):
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        label="Estado",
    )

    user_account = forms.ModelChoiceField(
        label="Cuenta de usuario",
        queryset=UserProfile.objects.none(),
        widget=AccountRolePreviewSelect(),
        required=False,
        help_text="Selecciona una cuenta para vincular al funcionario.",
    )

    assigned_roles_display = forms.CharField(
        label="Roles del usuario (automático)",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={"readonly": "readonly"}
        ),
    )

    class Meta(AccountsEmployeeForm.Meta):
        fields = [
            "name",
            "delegation",
            "position",
            "roles",
            "status",
            "user_account",
            "assigned_roles_display",
            "profile_photo",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        _configure_status_choices(self)

        self.fields["profile_photo"].help_text = (
            "Opcional. PNG, JPG o WebP."
        )

        self.fields["profile_photo"].widget.attrs.update({
            "accept": "image/png,image/jpeg,image/webp",
            "data-profile-photo-input": "",
        })

        # Cuentas activas disponibles para vincular.
        available = UserProfile.objects.filter(
            deleted_at__isnull=True,
            user__is_superuser=False,
        )

        if self.instance.pk:
            available = available.filter(
                Q(employee__isnull=True, user__is_active=True)
                | Q(employee=self.instance)
            )
        else:
            available = available.filter(
                employee__isnull=True,
                user__is_active=True,
            )

        self.fields["user_account"].queryset = (
            available
            .select_related("user", "delegation")
            .prefetch_related("user__groups")
            .order_by("user__username")
        )

        self.fields["user_account"].label_from_instance = (
            lambda profile: (
                f"{profile.user.username} "
                f"({profile.employee_code})"
            )
        )

        # Cuenta ya vinculada al funcionario.
        current_profile = None

        if self.instance.pk:
            current_profile = UserProfile.objects.filter(
                employee=self.instance,
                deleted_at__isnull=True,
            ).first()

        if current_profile:
            self.fields["user_account"].initial = current_profile.pk

        selected_id = (
            self.data.get(self.add_prefix("user_account"))
            if self.is_bound
            else (
                current_profile.pk
                if current_profile
                else None
            )
        )

        selected_profile = None

        if selected_id and str(selected_id).isdigit():
            selected_profile = (
                self.fields["user_account"]
                .queryset.filter(pk=selected_id)
                .first()
            )

        if selected_profile:
            self.fields["assigned_roles_display"].initial = (
                ", ".join(
                    group.name
                    for group in selected_profile.user.groups.all()
                )
            )

        self.apply_bootstrap()

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if len(name) < 2:
            raise ValidationError(
                "El nombre debe tener al menos 2 caracteres."
            )

        return name

    def clean_roles(self):
        roles = self.cleaned_data["roles"].strip()

        if len(roles) < 3:
            raise ValidationError(
                "La descripción de funciones debe tener "
                "al menos 3 caracteres."
            )

        return roles

    def clean(self):
        cleaned_data = super().clean()

        profile = cleaned_data.get("user_account")
        delegation = cleaned_data.get("delegation")

        if self.instance.pk and (
            Employee.objects.filter(pk=self.instance.pk, responsible_for_delegations__isnull=False).exists()
        ):
            if delegation and delegation.pk != self.instance.delegation_id:
                self.add_error("delegation", "Este empleado es responsable de una delegación; cambia primero el responsable.")
            if cleaned_data.get("status") not in ("Active", "Activo"):
                self.add_error("status", "Primero cambia el responsable de la delegación.")

        existing_profile = None

        if self.instance.pk:
            existing_profile = UserProfile.objects.filter(
                employee=self.instance,
                deleted_at__isnull=True,
            ).first()

        if existing_profile and (
            profile is None
            or profile.pk != existing_profile.pk
        ):
            self.add_error(
                "user_account",
                "No se puede quitar ni cambiar una cuenta ya vinculada.",
            )

        if profile and delegation:
            if not profile.authorized_delegations.filter(pk=delegation.pk).exists() and profile.delegation_id != delegation.pk:
                self.add_error(
                    "user_account",
                    "La cuenta debe pertenecer "
                    "a la misma delegación.",
                )

        return cleaned_data



class PositionForm(AccountsPositionForm):
    class Meta(AccountsPositionForm.Meta):
        pass

    def clean_position_name(self):
        name = self.cleaned_data["position_name"].strip()
        if len(name) < 3:
            raise ValidationError(
                "El nombre del cargo debe tener al menos 3 caracteres."
            )
        duplicates = PositionFunction.objects.filter(
            position_name__iexact=name,
            deleted_at__isnull=True,
        )
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError(
                "Ya existe un cargo activo con ese nombre."
            )
        return name

    def clean_measurable_items(self):
        value = self.cleaned_data["measurable_items"].strip()
        if len(value) < 2:
            raise ValidationError(
                "Indica al menos 2 caracteres para los ítems medibles."
            )
        return value

    def clean_services(self):
        value = self.cleaned_data["services"].strip()
        if len(value) < 2:
            raise ValidationError(
                "Indica al menos 2 caracteres para los servicios."
            )
        return value

    def clean_weightings(self):
        value = self.cleaned_data["weightings"].strip()
        if len(value) < 2:
            raise ValidationError(
                "Indica al menos 2 caracteres para las ponderaciones."
            )
        return value