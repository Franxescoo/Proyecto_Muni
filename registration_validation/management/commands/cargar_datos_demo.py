from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, MeasurementItem, Period
from registration_validation.forms import (
    ActivityForm,
    AttentionEntryForm,
    EvidenceForm,
    ValidationForm,
)
from registration_validation.models import (
    ActivityType,
    AttentionType,
    Service,
    SubAttention,
    AttentionEntry,
    Activity,
    Evidence,
    Validation,
)


DEMO_PREFIX = "DEMO SGR - "
DEMO_CODES = {
    "activity_type": "DEMOSGR-A01",
    "service": "DEMOSGR-S01",
    "measurement_item": "DEMOSGR-M01",
    "position": DEMO_PREFIX + "Cargo de Registro y Validación",
    "employee": DEMO_PREFIX + "Funcionario de Registro",
    "verifier": DEMO_PREFIX + "Funcionario Verificador",
    "attention_type": "DEMOSGR-T01",
    "sub_attention": "DEMOSGR-SA01",
    "goal": DEMO_PREFIX + "Meta de Registro y Validación",
}

TEST_USERNAME = "sgr_pruebas"
TEST_DELEGATION_CODE = "SGR-PRUEBAS-01"
TEST_EMPLOYEE_NAME = "Funcionario de Prueba SGR"

TEST_PERMISSIONS = (
    ("registration_validation", "view_activity"),
    ("registration_validation", "add_activity"),
    ("registration_validation", "change_activity"),
    ("registration_validation", "view_activitytype"),
    ("registration_validation", "view_evidence"),
    ("registration_validation", "add_evidence"),
    ("registration_validation", "change_evidence"),
    ("registration_validation", "view_validation"),
    ("registration_validation", "add_validation"),
    ("registration_validation", "change_validation"),
    ("registration_validation", "view_service"),
    ("registration_validation", "view_attentiontype"),
    ("registration_validation", "view_subattention"),
)


def _ensure_record(model, lookup, defaults, expected, label):
    try:
        instance, created = model.objects.get_or_create(
            **lookup,
            defaults=defaults,
        )
    except model.MultipleObjectsReturned as exc:
        raise CommandError(
            f"Hay varios registros para {label}; no se modificó nada."
        ) from exc

    mismatches = {
        field: getattr(instance, field)
        for field, value in expected.items()
        if getattr(instance, field) != value
    }
    if mismatches:
        raise CommandError(
            f"El registro existente de {label} no coincide con los datos "
            f"DEMO esperados ({', '.join(mismatches)}); no se modificó nada."
        )

    instance.full_clean()
    return instance, created


class Command(BaseCommand):
    help = (
        "Prepara catálogos y planificación DEMO para Registro y Validación. "
        "No crea actividades, evidencias, validaciones ni atenciones."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar",
            action="store_true",
            help="Aplicar la carga. Sin esta opción solo muestra el plan.",
        )

    def _verify_local_database(self):
        database = settings.DATABASES["default"]
        expected_path = (settings.BASE_DIR / "db.sqlite3").resolve()
        configured_path = Path(database["NAME"]).resolve()
        if not settings.DEBUG:
            raise CommandError("La carga solo se permite con DEBUG activo.")
        if database["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("La carga solo se permite sobre SQLite local.")
        if configured_path != expected_path:
            raise CommandError(
                "La base configurada no es db.sqlite3 del repositorio; "
                "se canceló la carga."
            )
        if not configured_path.is_file():
            raise CommandError("No existe la base SQLite local configurada.")
        self.stdout.write(f"Base local verificada: {configured_path}")

    def _get_prerequisites(self):
        try:
            user = get_user_model().objects.get(username=TEST_USERNAME)
            delegation = Delegation.objects.get(code=TEST_DELEGATION_CODE)
            profile = UserProfile.objects.select_related(
                "employee",
                "delegation",
            ).get(user=user)
        except (
            get_user_model().DoesNotExist,
            Delegation.DoesNotExist,
            UserProfile.DoesNotExist,
        ) as exc:
            raise CommandError(
                "Falta el usuario sgr_pruebas, su perfil o la delegación "
                "SGR-PRUEBAS-01. No se crearán usuarios ni delegaciones."
            ) from exc

        if not user.is_active or user.is_superuser:
            raise CommandError(
                "sgr_pruebas debe ser una cuenta activa no privilegiada."
            )
        if profile.delegation_id != delegation.pk:
            raise CommandError(
                "El perfil de sgr_pruebas no corresponde a "
                "SGR-PRUEBAS-01; no se cambiará el perfil."
            )
        if profile.employee_id is None:
            raise CommandError(
                "sgr_pruebas no tiene funcionario vinculado; no se cambiará "
                "el perfil existente."
            )
        if profile.employee.name != TEST_EMPLOYEE_NAME:
            raise CommandError(
                "El funcionario vinculado a sgr_pruebas no coincide con el "
                "funcionario de prueba esperado."
            )
        if profile.employee.delegation_id != delegation.pk:
            raise CommandError(
                "El funcionario vinculado y el perfil tienen delegaciones "
                "distintas."
            )
        if delegation.status.casefold() != "active":
            raise CommandError("La delegación de prueba no está activa.")

        authorized = set(
            profile.authorized_delegations.values_list("pk", flat=True)
        )
        if authorized and delegation.pk not in authorized:
            raise CommandError(
                "La delegación de prueba no está autorizada en el perfil."
            )
        return user, profile, delegation

    def _load_demo_data(self, user, profile, delegation):
        today = date.today()
        period_start = date(today.year, 1, 1)
        period_end = date(today.year, 12, 31)
        computable_days = sum(
            1
            for day in range((period_end - period_start).days + 1)
            if date.fromordinal(period_start.toordinal() + day).weekday() < 5
        )

        activity_type, _ = _ensure_record(
            ActivityType,
            {"code": "DEMOSGR-A01"},
            {
                "name": DEMO_PREFIX + "Actividad de atención",
                "description": "Clasificación ficticia para pruebas manuales.",
                "status": True,
            },
            {
                "name": DEMO_PREFIX + "Actividad de atención",
                "description": "Clasificación ficticia para pruebas manuales.",
                "status": True,
                "deleted_at": None,
            },
            "tipo de actividad",
        )
        service, _ = _ensure_record(
            Service,
            {"code": "DEMOSGR-S01"},
            {
                "name": DEMO_PREFIX + "Atención municipal",
                "description": "Servicio ficticio para pruebas manuales.",
                "status": True,
            },
            {
                "name": DEMO_PREFIX + "Atención municipal",
                "description": "Servicio ficticio para pruebas manuales.",
                "status": True,
                "deleted_at": None,
            },
            "servicio",
        )
        item, _ = _ensure_record(
            MeasurementItem,
            {"code": "DEMOSGR-M01"},
            {
                "name": DEMO_PREFIX + "Atenciones realizadas",
                "description": "Ítem ficticio para pruebas manuales.",
                "item_type": MeasurementItem.ItemType.QUANTITATIVE,
                "unit": "registros",
                "formula": "",
                "is_active": True,
            },
            {
                "name": DEMO_PREFIX + "Atenciones realizadas",
                "description": "Ítem ficticio para pruebas manuales.",
                "item_type": MeasurementItem.ItemType.QUANTITATIVE,
                "unit": "registros",
                "formula": "",
                "is_active": True,
                "deleted_at": None,
            },
            "ítem de medición",
        )

        position_name = DEMO_CODES["position"]
        position, position_created = _ensure_record(
            PositionFunction,
            {"position_name": position_name},
            {
                "measurable_items": DEMO_PREFIX + "DEMOSGR-M01",
                "services": DEMO_PREFIX + "DEMOSGR-S01",
                "weightings": "100%",
                "validity_start": period_start,
                "validity_end": period_end,
            },
            {
                "measurable_items": DEMO_PREFIX + "DEMOSGR-M01",
                "services": DEMO_PREFIX + "DEMOSGR-S01",
                "weightings": "100%",
                "validity_start": period_start,
                "validity_end": period_end,
                "deleted_at": None,
            },
            "cargo",
        )
        if position_created:
            position.catalog_items.add(item)
            position.catalog_services.add(service)
        elif (
            not position.catalog_items.filter(pk=item.pk).exists()
            or not position.catalog_services.filter(pk=service.pk).exists()
        ):
            raise CommandError(
                "El cargo DEMO existente no tiene sus relaciones de "
                "catálogo esperadas; no se modificará."
            )

        employees = {}
        for key, name in (
            ("employee", DEMO_CODES["employee"]),
            ("verifier", DEMO_CODES["verifier"]),
        ):
            employees[key], _ = _ensure_record(
                Employee,
                {"name": name, "delegation": delegation},
                {
                    "position": position,
                    "roles": "Funcionario DEMO de Registro y Validación",
                    "status": "Active",
                },
                {
                    "position_id": position.pk,
                    "roles": "Funcionario DEMO de Registro y Validación",
                    "status": "Active",
                    "deleted_at": None,
                },
                f"funcionario {key}",
            )

        period, _ = _ensure_record(
            Period,
            {"start_date": period_start, "end_date": period_end},
            {
                "computable_days": computable_days,
                "status": Period.Status.ACTIVE,
                "thresholds": "Parámetros ficticios DEMO para pruebas.",
                "parameters_version": f"demo-{today.year}",
            },
            {
                "computable_days": computable_days,
                "status": Period.Status.ACTIVE,
                "thresholds": "Parámetros ficticios DEMO para pruebas.",
                "parameters_version": f"demo-{today.year}",
                "deleted_at": None,
            },
            "período",
        )

        goal, _ = _ensure_record(
            Goal,
            {
                "period": period,
                "employee": employees["employee"],
                "position": position,
                "measurement_item": item,
            },
            {
                "item": DEMO_CODES["goal"],
                "objective_value": Decimal("10.00"),
                "required_evidence_count": 2,
                "unit": "registros",
                "weight": Decimal("100.00"),
            },
            {
                "item": DEMO_CODES["goal"],
                "objective_value": Decimal("10.00"),
                "required_evidence_count": 2,
                "unit": "registros",
                "weight": Decimal("100.00"),
                "deleted_at": None,
            },
            "meta",
        )

        attention_type, _ = _ensure_record(
            AttentionType,
            {"code": "DEMOSGR-T01"},
            {
                "name": DEMO_PREFIX + "Orientación municipal",
                "description": "Tipo ficticio para pruebas manuales.",
                "status": True,
            },
            {
                "name": DEMO_PREFIX + "Orientación municipal",
                "description": "Tipo ficticio para pruebas manuales.",
                "status": True,
                "deleted_at": None,
            },
            "tipo de atención",
        )
        sub_attention, _ = _ensure_record(
            SubAttention,
            {"code": "DEMOSGR-SA01"},
            {
                "name": DEMO_PREFIX + "Consulta general",
                "attention_type": attention_type,
                "status": True,
            },
            {
                "name": DEMO_PREFIX + "Consulta general",
                "attention_type_id": attention_type.pk,
                "status": True,
                "deleted_at": None,
            },
            "subatención",
        )

        required_permissions = []
        for app_label, codename in TEST_PERMISSIONS:
            try:
                required_permissions.append(
                    Permission.objects.get(
                        content_type__app_label=app_label,
                        codename=codename,
                    )
                )
            except Permission.DoesNotExist as exc:
                raise CommandError(
                    f"No existe el permiso requerido {app_label}.{codename}."
                ) from exc
        user.user_permissions.add(*required_permissions)
        user = get_user_model().objects.get(pk=user.pk)

        self._verify_form_options(
            user,
            delegation,
            profile,
            goal,
            employees,
            activity_type,
            attention_type,
            sub_attention,
        )

        return {
            "activity_type": activity_type,
            "service": service,
            "item": item,
            "position": position,
            "employees": employees,
            "period": period,
            "goal": goal,
            "attention_type": attention_type,
            "sub_attention": sub_attention,
            "user": user,
        }

    def _verify_form_options(
        self,
        user,
        delegation,
        profile,
        goal,
        employees,
        activity_type,
        attention_type,
        sub_attention,
    ):
        user.sgr_active_delegation_id = delegation.pk
        activity_form = ActivityForm(user=user)
        evidence_form = EvidenceForm(user=user)
        validation_form = ValidationForm(user=user)
        attention_form = AttentionEntryForm(user=user)

        checks = (
            (
                "meta disponible en Actividad",
                activity_form.fields["goal"].queryset.filter(
                    pk=goal.pk
                ).exists(),
            ),
            (
                "funcionario autor disponible en Actividad",
                activity_form.fields["author"].queryset.filter(
                    pk=employees["employee"].pk
                ).exists(),
            ),
            (
                "tipo DEMO disponible en Actividad",
                activity_form.fields["activity_type"].queryset.filter(
                    pk=activity_type.pk
                ).exists(),
            ),
            (
                "funcionario disponible en Evidencia",
                evidence_form.fields["author"].queryset.filter(
                    pk=employees["verifier"].pk
                ).exists(),
            ),
            (
                "verificador disponible en Validación",
                validation_form.fields["verifier"].queryset.filter(
                    pk=employees["verifier"].pk
                ).exists(),
            ),
            (
                "tipo DEMO disponible en Atención",
                attention_form.fields["attention_type"].queryset.filter(
                    pk=attention_type.pk
                ).exists(),
            ),
            (
                "subatención DEMO disponible en Atención",
                attention_form.fields["sub_attention"].queryset.filter(
                    pk=sub_attention.pk
                ).exists(),
            ),
            (
                "delegación disponible en Atención",
                attention_form.fields["delegation"].queryset.filter(
                    pk=delegation.pk
                ).exists(),
            ),
            (
                "funcionario vinculado disponible en Atención",
                profile.employee_id is not None
                and attention_form.fields[
                    "responsible_employee"
                ].queryset.filter(pk=profile.employee_id).exists(),
            ),
        )
        failed = [label for label, valid in checks if not valid]
        if failed:
            raise CommandError(
                "No se pudieron verificar opciones de formularios: "
                + ", ".join(failed)
            )

    def _write_summary(self, records):
        self.stdout.write(
            "Datos DEMO disponibles (se omiten deliberadamente "
            "actividades, evidencias, validaciones, atenciones y resoluciones):"
        )
        self.stdout.write(
            f"  Delegación reutilizada: {TEST_DELEGATION_CODE} — "
            f"{records['employees']['employee'].delegation.name}"
        )
        self.stdout.write(
            f"  Cargo: {records['position'].position_name}"
        )
        self.stdout.write(
            f"  Funcionarios: {records['employees']['employee'].name}; "
            f"{records['employees']['verifier'].name}"
        )
        self.stdout.write(
            f"  Período activo: {records['period'].start_date} a "
            f"{records['period'].end_date}"
        )
        self.stdout.write(
            f"  Meta: {records['goal'].item} — funcionario "
            f"{records['goal'].employee.name}"
        )
        self.stdout.write(
            f"  Ítem: {records['item'].code} — {records['item'].name}"
        )
        self.stdout.write(
            f"  Tipo de actividad: {records['activity_type'].code} — "
            f"{records['activity_type'].name}"
        )
        self.stdout.write(
            f"  Servicio: {records['service'].code} — "
            f"{records['service'].name}"
        )
        self.stdout.write(
            f"  Atención: {records['attention_type'].code} - "
            f"{records['sub_attention'].code}"
        )
        self.stdout.write(
            f"  Usuario: {records['user'].username}; permisos de prueba "
            "limitados a Registro y Validación."
        )

    def handle(self, *args, **options):
        self._verify_local_database()
        user, profile, delegation = self._get_prerequisites()
        self.stdout.write(
            f"Se reutilizan usuario={user.username}, delegación="
            f"{delegation.code}, funcionario vinculado="
            f"{profile.employee.name}."
        )
        self.stdout.write(
            "Registros principales actuales: "
            f"actividades={Activity.objects.count()}, "
            f"evidencias={Evidence.objects.count()}, "
            f"validaciones={Validation.objects.count()}, "
            f"atenciones={AttentionEntry.objects.count()}."
        )

        if not options["aplicar"]:
            self.stdout.write(
                self.style.WARNING(
                    "SIMULACIÓN: no se modificó la base. "
                    "Usa --aplicar para crear los datos de apoyo."
                )
            )
            return

        with transaction.atomic():
            records = self._load_demo_data(user, profile, delegation)
            self._write_summary(records)
        self.stdout.write(
            self.style.SUCCESS(
                "Carga DEMO aplicada. No se crearon ni modificaron "
                "registros principales."
            )
        )
