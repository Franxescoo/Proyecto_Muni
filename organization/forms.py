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

from .models import Delegation, OrganizationRole, PositionFunction

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
    delegation = forms.ModelChoiceField(
        label="Delegación",
        queryset=Delegation.objects.filter(
            deleted_at__isnull=True
        ).order_by("name"),
    )
    permissions = forms.ModelMultipleChoiceField(
        label="Permisos",
        queryset=Permission.objects.filter(
            content_type__app_label__in=[
                "organization",
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
        initial = dict(kwargs.pop("initial", {}))
        bound_data = args[0] if args else kwargs.get("data")
        if self.group and bound_data is None:
            initial.setdefault("name", self.group.name)
            initial.setdefault("permissions", self.group.permissions.all())
            role = OrganizationRole.objects.filter(
                group=self.group
            ).select_related("delegation").first()
            if role:
                initial.setdefault("delegation", role.delegation_id)
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicate = Group.objects.filter(name__iexact=name)
        if self.group:
            duplicate = duplicate.exclude(pk=self.group.pk)
        if duplicate.exists():
            raise ValidationError("Ya existe un rol con ese nombre.")
        return name

    def save(self):
        with transaction.atomic():
            group = self.group or Group()
            group.name = self.cleaned_data["name"]
            group.save()
            group.permissions.set(self.cleaned_data["permissions"])
            OrganizationRole.objects.update_or_create(
                group=group,
                defaults={"delegation": self.cleaned_data["delegation"]},
            )
        return group


class DelegationForm(BootstrapMixin, forms.ModelForm):
    status = forms.ChoiceField(choices=STATUS_CHOICES, label="Estado")

    class Meta:
        model = Delegation
        fields = ["name", "scope", "status"]
        labels = {
            "name": "Nombre de la delegación",
            "scope": "Ámbito",
            "status": "Estado",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Ej. Delegación Centro"}
            ),
            "scope": forms.TextInput(
                attrs={"placeholder": "Ej. Urbano o rural"}
            ),
            "status": forms.TextInput(
                attrs={"placeholder": "Ej. Active"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()
        _configure_status_choices(self)

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


class EmployeeForm(AccountsEmployeeForm):
    status = forms.ChoiceField(choices=STATUS_CHOICES, label="Estado")
    assigned_groups = forms.ModelMultipleChoiceField(
        label="Roles asignados",
        queryset=Group.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Los permisos de estos roles se aplican a la cuenta vinculada.",
    )

    class Meta(AccountsEmployeeForm.Meta):
        fields = [
            "name",
            "delegation",
            "position",
            "roles",
            "status",
            "assigned_groups",
            "profile_photo",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _configure_status_choices(self)
        self.fields["profile_photo"].help_text = "Opcional. PNG, JPG o WebP."
        self.fields["profile_photo"].widget.attrs.update(
            {
                "accept": "image/png,image/jpeg,image/webp",
                "data-profile-photo-input": "",
            }
        )
        if self.instance.pk:
            current_group_ids = self.instance.assigned_groups.values_list(
                "pk", flat=True
            )
            self.fields["assigned_groups"].queryset = Group.objects.filter(
                Q(organization_role__delegation_id=self.instance.delegation_id)
                | Q(pk__in=current_group_ids)
            ).order_by("name")
        else:
            self.fields["assigned_groups"].queryset = Group.objects.filter(
                organization_role__isnull=False
            ).select_related(
                "organization_role__delegation"
            ).order_by(
                "organization_role__delegation__name",
                "name",
            )

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
                "La descripción de funciones debe tener al menos 3 caracteres."
            )
        return roles

    def clean_assigned_groups(self):
        groups = self.cleaned_data["assigned_groups"]
        delegation = self.cleaned_data.get("delegation")
        if delegation is None:
            return groups

        existing_ids = set()
        if self.instance.pk:
            existing_ids = set(
                self.instance.assigned_groups.values_list("pk", flat=True)
            )

        for group in groups:
            role = OrganizationRole.objects.filter(group=group).first()
            if role is None:
                if group.pk not in existing_ids:
                    raise ValidationError(
                        "Asigna primero este rol a una delegación."
                    )
            elif role.delegation_id != delegation.pk:
                raise ValidationError(
                    "Solo puedes asignar roles de la delegación del funcionario."
                )
        return groups


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