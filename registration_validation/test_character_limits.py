from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period

from .forms import (
    ActivityForm,
    ActivityTypeForm,
    AttentionEntryForm,
    AttentionTypeForm,
    EvidenceForm,
    ServiceForm,
    SubAttentionForm,
    ValidationForm,
)
from .models import (
    Activity,
    ActivityType,
    AttentionEntry,
    AttentionType,
    Evidence,
    Service,
    SubAttention,
    Validation,
)


FIELD_LIMITS = {
    ActivityForm: {
        "request_problem": 2000,
        "action": 2000,
        "contact": 150,
        "phone": 20,
    },
    EvidenceForm: {
        "code": 100,
        "file_link": 500,
        "review_status": 50,
    },
    ValidationForm: {
        "decision": 50,
        "observation": 1000,
        "result": 100,
    },
    ActivityTypeForm: {
        "code": 50,
        "name": 150,
        "description": 300,
    },
    ServiceForm: {
        "code": 50,
        "name": 150,
        "description": 300,
    },
    AttentionTypeForm: {
        "code": 50,
        "name": 150,
        "description": 300,
    },
    SubAttentionForm: {
        "code": 50,
        "name": 150,
    },
    AttentionEntryForm: {
        "requester": 150,
        "requester_email": 254,
        "requester_phone": 25,
        "address": 250,
        "subject": 160,
        "description": 4000,
        "closing_observation": 1000,
        "citizen_rut": 16,
    },
}


class RegistrationCharacterLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(
            code="LIM-N",
            name="Delegación Límites",
            status="Active",
            scope="Urbana",
        )
        cls.position = PositionFunction.objects.create(
            position_name="Funcionario",
            measurable_items="Atenciones",
            services="Ventanilla",
            weightings="100",
            validity_start=date(2026, 1, 1),
            validity_end=date(2027, 12, 31),
        )
        cls.employee = Employee.objects.create(
            name="Funcionario de prueba",
            delegation=cls.delegation,
            position=cls.position,
            roles="Registro",
            status="Active",
        )
        cls.period = Period.objects.create(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            computable_days=250,
            thresholds="Green >= 90, Yellow >= 60",
            parameters_version="1.0",
        )
        cls.goal = Goal.objects.create(
            period=cls.period,
            employee=cls.employee,
            position=cls.position,
            item="Meta de prueba",
            objective_value=10,
            unit="Registros",
            weight=50,
        )
        cls.activity_type = ActivityType.objects.create(
            code="LIM-ACT",
            name="Tipo de actividad",
        )
        cls.attention_type = AttentionType.objects.create(
            code="LIM-ATT",
            name="Tipo de atención",
        )
        cls.sub_attention = SubAttention.objects.create(
            code="LIM-SUB",
            name="Subatención",
            attention_type=cls.attention_type,
        )

    def activity_data(self, **overrides):
        data = {
            "goal": self.goal.pk,
            "author": self.employee.pk,
            "activity_type": self.activity_type.pk,
            "date": "2026-06-01",
            "request_problem": "Solicitud",
            "action": "Acción",
            "contact": "Contacto",
            "phone": "55512345",
            "status": "Pending",
        }
        data.update(overrides)
        return data

    def attention_entry_data(self, **overrides):
        data = {
            "requester": "Solicitante",
            "requester_email": "",
            "requester_phone": "55512345",
            "address": "Dirección",
            "subject": "Asunto",
            "attention_type": self.attention_type.pk,
            "sub_attention": self.sub_attention.pk,
            "description": "Descripción",
            "delegation": self.delegation.pk,
            "responsible_employee": self.employee.pk,
            "citizen_rut": "",
            "confirm_citizen_change": "",
        }
        data.update(overrides)
        return data

    def make_attention_entry(self, **overrides):
        values = {
            "origin": "INTERNAL",
            "status": "IN_PROGRESS",
            "requester": "Solicitante",
            "requester_email": "",
            "requester_phone": "55512345",
            "address": "Dirección",
            "subject": "Asunto",
            "attention_type": self.attention_type,
            "sub_attention": self.sub_attention,
            "description": "Descripción",
            "delegation": self.delegation,
            "responsible_employee": self.employee,
        }
        values.update(overrides)
        return AttentionEntry.objects.create(**values)

    def test_all_text_fields_enforce_server_and_html_limits(self):
        for form_class, fields in FIELD_LIMITS.items():
            form = (
                AttentionEntryForm(
                    instance=self.make_attention_entry()
                )
                if form_class is AttentionEntryForm
                else form_class()
            )
            for field_name, limit in fields.items():
                boundary_value = (
                    "a" * 64
                    + "@"
                    + ".".join(("b" * 63, "c" * 63, "d" * 61))
                    if field_name == "requester_email"
                    else "x" * limit
                )
                with self.subTest(
                    form=form_class.__name__,
                    field=field_name,
                    case="limit",
                ):
                    field = form.fields[field_name]
                    self.assertEqual(
                        field.widget.attrs.get("maxlength"),
                        limit,
                    )
                    self.assertIn(
                        f'maxlength="{limit}"',
                        str(form[field_name]),
                    )
                    self.assertEqual(
                        field.clean(boundary_value),
                        boundary_value,
                    )
                with self.subTest(
                    form=form_class.__name__,
                    field=field_name,
                    case="over-limit",
                ):
                    with self.assertRaises(ValidationError):
                        form.fields[field_name].clean(
                            boundary_value + "x"
                        )

    def test_required_text_fields_reject_empty_values_in_spanish(self):
        for form_class, fields in (
            (ActivityForm, ("request_problem", "action", "contact", "phone")),
            (ValidationForm, ("decision", "result")),
            (ActivityTypeForm, ("code", "name")),
            (AttentionTypeForm, ("code", "name")),
            (SubAttentionForm, ("code", "name")),
            (AttentionEntryForm, ("requester", "description")),
        ):
            form = form_class()
            for field_name in fields:
                with self.subTest(
                    form=form_class.__name__,
                    field=field_name,
                ):
                    with self.assertRaises(ValidationError) as context:
                        form.fields[field_name].clean("")
                    self.assertIn(
                        "obligatorio",
                        str(context.exception).lower(),
                    )

    def test_model_full_clean_enforces_textfield_limits_without_blocking_legacy_values(self):
        activity = Activity(
            goal=self.goal,
            author=self.employee,
            activity_type=self.activity_type,
            date=date(2026, 6, 1),
            request_problem="p" * 2001,
            action="Acción",
            contact="Contacto",
            phone="555",
        )
        with self.assertRaises(ValidationError) as context:
            activity.full_clean()
        self.assertIn("request_problem", context.exception.message_dict)

        legacy_type = ActivityType.objects.create(
            code="LIM-LEGACY",
            name="Tipo histórico",
            description="d" * 301,
        )
        legacy_type.name = "Tipo histórico actualizado"
        legacy_type.full_clean()

    def test_activity_creation_and_edit_enforce_text_boundaries(self):
        exact_data = self.activity_data(
            request_problem="p" * 2000,
            action="a" * 2000,
        )
        create_form = ActivityForm(data=exact_data)
        self.assertTrue(create_form.is_valid(), create_form.errors)

        invalid_create = ActivityForm(
            data=self.activity_data(request_problem="p" * 2001)
        )
        self.assertFalse(invalid_create.is_valid())
        self.assertIn("request_problem", invalid_create.errors)

        activity = Activity.objects.create(
            goal=self.goal,
            author=self.employee,
            activity_type=self.activity_type,
            date=date(2026, 6, 1),
            request_problem="Original",
            action="Original",
            contact="Contacto",
            phone="555",
        )
        edit_form = ActivityForm(
            data=self.activity_data(
                request_problem="p" * 2000,
                action="a" * 2000,
            ),
            instance=activity,
        )
        self.assertTrue(edit_form.is_valid(), edit_form.errors)

        invalid_edit = ActivityForm(
            data=self.activity_data(action="a" * 2001),
            instance=activity,
        )
        self.assertFalse(invalid_edit.is_valid())
        self.assertIn("action", invalid_edit.errors)

    def test_attention_entry_creation_and_edit_enforce_description_and_closing_limits(self):
        create_form = AttentionEntryForm(
            data=self.attention_entry_data(description="d" * 4000)
        )
        self.assertTrue(create_form.is_valid(), create_form.errors)

        invalid_create = AttentionEntryForm(
            data=self.attention_entry_data(description="d" * 4001)
        )
        self.assertFalse(invalid_create.is_valid())
        self.assertIn("description", invalid_create.errors)

        entry = self.make_attention_entry(
            description="Descripción original"
        )
        edit_data = self.attention_entry_data(
            description="d" * 4000,
            status="RESOLVED",
            closing_observation="r" * 1000,
        )
        edit_form = AttentionEntryForm(data=edit_data, instance=entry)
        self.assertTrue(edit_form.is_valid(), edit_form.errors)

        invalid_edit = AttentionEntryForm(
            data=self.attention_entry_data(
                status="RESOLVED",
                closing_observation="r" * 1001,
            ),
            instance=entry,
        )
        self.assertFalse(invalid_edit.is_valid())
        self.assertIn("closing_observation", invalid_edit.errors)

    def test_validation_version_minimum_is_enforced_by_form_and_model(self):
        activity = Activity.objects.create(
            goal=self.goal,
            author=self.employee,
            activity_type=self.activity_type,
            date=date(2026, 6, 1),
            request_problem="Solicitud",
            action="Acción",
            contact="Contacto",
            phone="555",
        )
        evidence = Evidence.objects.create(
            code="LIM-EVID",
            activity=activity,
            author=self.employee,
            date=timezone.now(),
        )
        form_data = {
            "evidence": evidence.pk,
            "verifier": self.employee.pk,
            "decision": "Aprobada",
            "date": "2026-06-01T10:00",
            "observation": "",
            "result": "Conforme",
            "version": "0",
        }
        form = ValidationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("version", form.errors)

        invalid_validation = Validation(
            evidence=evidence,
            verifier=self.employee,
            decision="Aprobada",
            date=timezone.now(),
            result="Conforme",
            version=0,
        )
        with self.assertRaises(ValidationError) as context:
            invalid_validation.full_clean()
        self.assertIn("version", context.exception.message_dict)
        with self.assertRaises(ValidationError):
            invalid_validation.save()

        valid_form = ValidationForm(data={**form_data, "version": "1"})
        self.assertTrue(valid_form.is_valid(), valid_form.errors)

        historical_validation = Validation(
            evidence=evidence,
            verifier=self.employee,
            decision="Histórica",
            date=timezone.now(),
            result="Conservada",
            version=0,
        )
        Validation.objects.bulk_create([historical_validation])
        historical_validation = Validation.objects.get(
            pk=historical_validation.pk
        )
        historical_validation.decision = "Actualizada"
        historical_validation.save(update_fields=("decision",))
        self.assertEqual(
            Validation.objects.get(
                pk=historical_validation.pk
            ).version,
            0,
        )
