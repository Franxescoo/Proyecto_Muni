from datetime import date
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import RequestFactory, TestCase
from django.utils import timezone
from django.utils.datastructures import MultiValueDict

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period

from .admin import archive_evidences
from .forms import ActivityForm, EvidenceForm, ValidationForm
from .models import (
    Activity,
    ActivityType,
    AttentionEntry,
    AttentionType,
    Evidence,
    SubAttention,
    Validation,
)
from .views import EvidenceCreateView, EvidenceUpdateView


class RegistrationRelationshipIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.north = Delegation.objects.create(
            code="REL-N",
            name="Delegación Norte",
            status="Active",
            scope="Urbana",
        )
        cls.south = Delegation.objects.create(
            code="REL-S",
            name="Delegación Sur",
            status="Active",
            scope="Rural",
        )
        cls.position = PositionFunction.objects.create(
            position_name="Funcionario de registro",
            measurable_items="Atenciones",
            services="Ventanilla",
            weightings="100",
            validity_start=date(2026, 1, 1),
            validity_end=date(2027, 12, 31),
        )
        cls.north_employee = Employee.objects.create(
            name="Funcionario Norte",
            delegation=cls.north,
            position=cls.position,
            roles="Registro",
            status="Active",
        )
        cls.north_employee_other = Employee.objects.create(
            name="Segundo funcionario Norte",
            delegation=cls.north,
            position=cls.position,
            roles="Registro",
            status="Active",
        )
        cls.south_employee = Employee.objects.create(
            name="Funcionario Sur",
            delegation=cls.south,
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
        cls.north_goal = Goal.objects.create(
            period=cls.period,
            employee=cls.north_employee,
            position=cls.position,
            item="Meta Norte",
            objective_value=10,
            unit="Registros",
            weight=50,
        )
        cls.north_goal_other = Goal.objects.create(
            period=cls.period,
            employee=cls.north_employee_other,
            position=cls.position,
            item="Otra meta Norte",
            objective_value=10,
            unit="Registros",
            weight=50,
        )
        cls.south_goal = Goal.objects.create(
            period=cls.period,
            employee=cls.south_employee,
            position=cls.position,
            item="Meta Sur",
            objective_value=10,
            unit="Registros",
            weight=50,
        )
        cls.activity_type = ActivityType.objects.create(
            code="REL-ACT",
            name="Actividad de prueba",
        )
        cls.attention_type = AttentionType.objects.create(
            code="REL-ATT",
            name="Atención de prueba",
        )
        cls.sub_attention = SubAttention.objects.create(
            code="REL-SUB",
            name="Subatención de prueba",
            attention_type=cls.attention_type,
        )
        cls.north_attention = AttentionEntry.objects.create(
            origin="INTERNAL",
            requester="Solicitante de prueba",
            attention_type=cls.attention_type,
            sub_attention=cls.sub_attention,
            description="Atención de prueba",
            delegation=cls.north,
        )

    def make_activity(self, goal=None, author=None, **kwargs):
        values = {
            "goal": goal or self.north_goal,
            "author": author or self.north_employee,
            "date": date(2026, 6, 1),
            "request_problem": "Solicitud de prueba",
            "action": "Acción de prueba",
            "contact": "Contacto de prueba",
            "phone": "55512345",
        }
        values.update(kwargs)
        return Activity.objects.create(**values)

    def make_evidence(self, activity=None, author=None, code=None):
        values = {
            "activity": activity or self.make_activity(),
            "author": author or self.north_employee,
            "file_link": "evidence/test",
            "date": timezone.now(),
        }
        if code is not None:
            values["code"] = code
        return Evidence.objects.create(**values)

    def make_validation(
        self,
        evidence=None,
        verifier=None,
        version=1,
    ):
        return Validation.objects.create(
            evidence=evidence or self.make_evidence(),
            verifier=verifier or self.north_employee,
            decision="Approved",
            date=timezone.now(),
            result="Approved",
            version=version,
        )

    @staticmethod
    def evidence_files():
        return MultiValueDict(
            {
                "new_files": [
                    SimpleUploadedFile("first.pdf", b"first"),
                    SimpleUploadedFile("second.pdf", b"second"),
                ]
            }
        )

    def activity_form_data(self, goal, author):
        return {
            "goal": goal.pk,
            "author": author.pk,
            "activity_type": self.activity_type.pk,
            "attention": self.north_attention.pk,
            "date": "2026-06-01",
            "request_problem": "Solicitud de prueba",
            "action": "Acción de prueba",
            "contact": "Contacto de prueba",
            "phone": "55512345",
            "status": "Pending",
        }

    def evidence_form_data(self, activity, author, code="REL-FORM-EVID"):
        return {
            "code": code,
            "activity": activity.pk,
            "author": author.pk,
            "file_link": "evidence/form",
            "date": "2026-06-01T10:00",
            "review_status": "Pending",
        }

    def validation_form_data(
        self,
        evidence,
        verifier,
        version=1,
    ):
        return {
            "evidence": evidence.pk,
            "verifier": verifier.pk,
            "decision": "Approved",
            "date": "2026-06-01T10:00",
            "observation": "",
            "result": "Approved",
            "version": version,
        }

    def test_activity_accepts_exact_goal_employee_and_rejects_other_author(self):
        activity = Activity(
            goal=self.north_goal,
            author=self.north_employee,
            date=date(2026, 6, 1),
            request_problem="Solicitud",
            action="Acción",
            contact="Contacto",
            phone="555",
        )
        activity.full_clean()
        activity.save()

        invalid = Activity(
            goal=self.north_goal,
            author=self.north_employee_other,
            date=date(2026, 6, 1),
            request_problem="Solicitud",
            action="Acción",
            contact="Contacto",
            phone="555",
        )
        with self.assertRaises(ValidationError) as context:
            invalid.full_clean()
        self.assertIn("author", context.exception.message_dict)

        with self.assertRaises(ValidationError):
            Activity.objects.create(
                goal=self.north_goal,
                author=self.north_employee_other,
                date=date(2026, 6, 1),
                request_problem="Solicitud",
                action="Acción",
                contact="Contacto",
                phone="555",
            )

    def test_activity_form_validates_creation_and_relationship_updates(self):
        valid_form = ActivityForm(
            data=self.activity_form_data(
                self.north_goal,
                self.north_employee,
            )
        )
        self.assertTrue(valid_form.is_valid(), valid_form.errors)

        invalid_form = ActivityForm(
            data=self.activity_form_data(
                self.north_goal,
                self.north_employee_other,
            )
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("author", invalid_form.errors)

        existing = self.make_activity()
        invalid_update = ActivityForm(
            data=self.activity_form_data(
                self.north_goal,
                self.north_employee_other,
            ),
            instance=existing,
        )
        self.assertFalse(invalid_update.is_valid())
        self.assertIn("author", invalid_update.errors)

    def test_activity_update_cannot_move_to_another_goal(self):
        activity = self.make_activity()
        activity.goal = self.north_goal_other
        activity.author = self.north_employee_other

        with self.assertRaises(ValidationError) as context:
            activity.save()
        self.assertIn("goal", context.exception.message_dict)

    def test_activity_save_rejects_invalid_update_but_allows_unrelated_legacy_edit(self):
        activity = self.make_activity()
        activity.author = self.south_employee
        with self.assertRaises(ValidationError):
            activity.save()

        legacy = Activity(
            goal=self.north_goal,
            author=self.south_employee,
            date=date(2026, 6, 1),
            request_problem="Histórica",
            action="Acción",
            contact="Contacto",
            phone="555",
        )
        Activity.objects.bulk_create([legacy])
        legacy = Activity.objects.get(pk=legacy.pk)
        legacy.action = "Texto actualizado"
        legacy.save(update_fields=("action",))
        self.assertEqual(
            Activity.objects.get(pk=legacy.pk).action,
            "Texto actualizado",
        )

    def test_activity_ignores_in_memory_relation_excluded_from_update_fields(self):
        activity = self.make_activity()
        original_author_id = activity.author_id
        activity.author = self.south_employee
        activity.action = "Acción actualizada"

        activity.save(update_fields=("action",))

        activity.refresh_from_db()
        self.assertEqual(activity.author_id, original_author_id)
        self.assertEqual(activity.action, "Acción actualizada")

    def test_activity_rejects_invalid_relation_included_in_update_fields(self):
        activity = self.make_activity()
        original_author_id = activity.author_id
        activity.author = self.north_employee_other

        with self.assertRaises(ValidationError):
            activity.save(update_fields=("author",))

        activity.refresh_from_db()
        self.assertEqual(activity.author_id, original_author_id)

    def test_activity_validates_included_relation_against_persisted_excluded_relation(self):
        activity = self.make_activity()
        original_goal_id = activity.goal_id
        activity.goal = self.north_goal_other
        activity.author = self.north_employee_other

        with self.assertRaises(ValidationError):
            activity.save(update_fields=("author",))

        activity.refresh_from_db()
        self.assertEqual(activity.goal_id, original_goal_id)
        self.assertEqual(activity.author_id, self.north_employee.pk)

    def test_activity_allows_normal_unrelated_field_update_fields_save(self):
        activity = self.make_activity()
        activity.action = "Acción no relacional"

        activity.save(update_fields=("action",))

        activity.refresh_from_db()
        self.assertEqual(activity.action, "Acción no relacional")
        self.assertEqual(activity.author_id, self.north_employee.pk)
        self.assertEqual(activity.goal_id, self.north_goal.pk)

    def test_evidence_and_validation_ignore_excluded_in_memory_relations(self):
        evidence = self.make_evidence()
        original_activity_id = evidence.activity_id
        south_activity = self.make_activity(
            goal=self.south_goal,
            author=self.south_employee,
        )
        evidence.activity = south_activity
        evidence.file_link = "evidence/updated"
        evidence.save(update_fields=("file_link",))

        evidence.refresh_from_db()
        self.assertEqual(evidence.activity_id, original_activity_id)
        self.assertEqual(evidence.file_link, "evidence/updated")

        validation = self.make_validation(evidence=evidence)
        original_evidence_id = validation.evidence_id
        south_evidence = self.make_evidence(
            activity=south_activity,
            author=self.south_employee,
            code="REL-EVID-UPDATE-FIELDS",
        )
        validation.evidence = south_evidence
        validation.decision = "Revised"
        validation.save(update_fields=("decision",))

        validation.refresh_from_db()
        self.assertEqual(validation.evidence_id, original_evidence_id)
        self.assertEqual(validation.decision, "Revised")

    def test_evidence_and_validation_use_persisted_excluded_relations(self):
        evidence = self.make_evidence()
        original_activity_id = evidence.activity_id
        south_activity = self.make_activity(
            goal=self.south_goal,
            author=self.south_employee,
        )
        evidence.activity = south_activity
        evidence.author = self.north_employee_other
        evidence.save(update_fields=("author",))

        evidence.refresh_from_db()
        self.assertEqual(evidence.activity_id, original_activity_id)
        self.assertEqual(evidence.author_id, self.north_employee_other.pk)

        validation = self.make_validation(evidence=evidence)
        original_evidence_id = validation.evidence_id
        south_evidence = self.make_evidence(
            activity=south_activity,
            author=self.south_employee,
            code="REL-EVID-VALIDATION-UPDATE-FIELDS",
        )
        validation.evidence = south_evidence
        validation.verifier = self.north_employee_other
        validation.save(update_fields=("verifier",))

        validation.refresh_from_db()
        self.assertEqual(validation.evidence_id, original_evidence_id)
        self.assertEqual(validation.verifier_id, self.north_employee_other.pk)

    def test_admin_queryset_update_archives_without_changing_relations(self):
        evidence = self.make_evidence()
        activity_id = evidence.activity_id
        author_id = evidence.author_id

        archive_evidences(
            None,
            None,
            Evidence.objects.filter(pk=evidence.pk),
        )

        evidence.refresh_from_db()
        self.assertIsNotNone(evidence.deleted_at)
        self.assertEqual(evidence.activity_id, activity_id)
        self.assertEqual(evidence.author_id, author_id)

    def test_evidence_accepts_activity_author_and_other_employee_same_delegation(self):
        activity = self.make_activity()
        same_author = self.make_evidence(activity, self.north_employee)
        other_author = self.make_evidence(
            activity,
            self.north_employee_other,
            code="REL-EVID-OTHER-NORTH",
        )
        self.assertEqual(same_author.author_id, activity.author_id)
        self.assertEqual(
            other_author.author.delegation_id,
            activity.author.delegation_id,
        )

    def test_evidence_rejects_author_from_another_delegation(self):
        activity = self.make_activity()
        evidence = Evidence(
            code="REL-EVID-CROSS",
            activity=activity,
            author=self.south_employee,
            date=timezone.now(),
        )
        with self.assertRaises(ValidationError) as context:
            evidence.full_clean()
        self.assertIn("author", context.exception.message_dict)

        with self.assertRaises(ValidationError):
            Evidence.objects.create(
                code="REL-EVID-CROSS-CREATE",
                activity=activity,
                author=self.south_employee,
                date=timezone.now(),
            )

    def test_evidence_form_validates_creation_and_relationship_updates(self):
        activity = self.make_activity()
        allowed_form = EvidenceForm(
            data=self.evidence_form_data(
                activity,
                self.north_employee_other,
            ),
            files=self.evidence_files(),
        )
        self.assertTrue(allowed_form.is_valid(), allowed_form.errors)

        invalid_form = EvidenceForm(
            data=self.evidence_form_data(
                activity,
                self.south_employee,
                code="REL-FORM-EVID-CROSS",
            ),
            files=self.evidence_files(),
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("author", invalid_form.errors)

        existing = self.make_evidence(
            activity,
            self.north_employee,
            code="REL-EVID-UPDATE",
        )
        invalid_update = EvidenceForm(
            data=self.evidence_form_data(
                activity,
                self.south_employee,
                code=existing.code,
            ),
            files=self.evidence_files(),
            instance=existing,
        )
        self.assertFalse(invalid_update.is_valid())
        self.assertIn("author", invalid_update.errors)

    def test_evidence_review_status_selector_accepts_predefined_and_historical_values(self):
        activity = self.make_activity()
        create_data = self.evidence_form_data(
            activity,
            self.north_employee,
        )
        create_data["review_status"] = "Observed"
        create_form = EvidenceForm(
            data=create_data,
            files=self.evidence_files(),
        )
        self.assertIn("<select", str(create_form["review_status"]))
        self.assertEqual(
            dict(create_form.fields["review_status"].widget.choices)[
                "Observed"
            ],
            "Con observaciones",
        )
        self.assertTrue(create_form.is_valid(), create_form.errors)

        invalid_form = EvidenceForm(
            data=dict(create_data, review_status="Unrecognized"),
            files=self.evidence_files(),
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("review_status", invalid_form.errors)

        existing = self.make_evidence(
            activity,
            self.north_employee,
            code="REL-EVID-LEGACY-STATUS",
        )
        existing.review_status = "Legacy review state"
        existing.save(update_fields=("review_status",))
        update_data = self.evidence_form_data(
            activity,
            self.north_employee,
            code=existing.code,
        )
        update_data["review_status"] = existing.review_status
        update_form = EvidenceForm(
            data=update_data,
            files=self.evidence_files(),
            instance=existing,
        )
        self.assertIn(
            "Legacy review state",
            dict(update_form.fields["review_status"].widget.choices),
        )
        self.assertTrue(update_form.is_valid(), update_form.errors)

    def test_evidence_code_is_generated_and_unique_when_omitted(self):
        first = self.make_evidence()
        second = self.make_evidence()

        self.assertRegex(first.code, r"^EVID-[0-9A-F]{32}$")
        self.assertRegex(second.code, r"^EVID-[0-9A-F]{32}$")
        self.assertNotEqual(first.code, second.code)
        self.assertEqual(Evidence.objects.filter(code=first.code).count(), 1)

    def test_evidence_code_is_immutable_and_respects_update_fields(self):
        evidence = self.make_evidence()
        original_code = evidence.code

        evidence.file_link = "evidence/updated"
        evidence.save()
        evidence.refresh_from_db()
        self.assertEqual(evidence.code, original_code)

        evidence.code = "MANUALLY-CHANGED"
        with self.assertRaises(ValidationError):
            evidence.save()
        evidence.refresh_from_db()
        self.assertEqual(evidence.code, original_code)

        evidence.code = "EXCLUDED-FIELD-CHANGE"
        evidence.file_link = "evidence/update-fields"
        evidence.save(update_fields=("file_link",))
        self.assertEqual(evidence.code, original_code)
        evidence.refresh_from_db()
        self.assertEqual(evidence.code, original_code)
        self.assertEqual(evidence.file_link, "evidence/update-fields")

        evidence.code = "INCLUDED-FIELD-CHANGE"
        with self.assertRaises(ValidationError):
            evidence.save(update_fields=("code",))
        evidence.refresh_from_db()
        self.assertEqual(evidence.code, original_code)

    def test_evidence_form_generates_code_without_accepting_manual_input(self):
        activity = self.make_activity()
        form_data = self.evidence_form_data(
            activity,
            self.north_employee,
            code="FORGED-MANUAL-CODE",
        )
        form = EvidenceForm(
            data=form_data,
            files=self.evidence_files(),
        )

        self.assertTrue(form.fields["code"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        evidence = form.save()

        self.assertRegex(evidence.code, r"^EVID-[0-9A-F]{32}$")
        self.assertNotEqual(evidence.code, "FORGED-MANUAL-CODE")

    def test_evidence_admin_displays_but_does_not_edit_generated_code(self):
        user = get_user_model().objects.create_superuser(
            username="evidence-code-admin",
            password="test-password",
        )
        request = RequestFactory().post("/admin/")
        request.user = user
        evidence_admin = admin.site._registry[Evidence]

        self.assertIn("code", evidence_admin.get_readonly_fields(request))
        add_form = evidence_admin.get_form(request, obj=None)
        self.assertNotIn("code", add_form.base_fields)

        evidence = Evidence(
            activity=self.make_activity(),
            author=self.north_employee,
            file_link="evidence/admin",
            date=timezone.now(),
        )
        evidence_admin.save_model(
            request,
            evidence,
            form=None,
            change=False,
        )
        self.assertRegex(evidence.code, r"^EVID-[0-9A-F]{32}$")

    def test_evidence_code_generation_retries_on_collision(self):
        existing = self.make_evidence(code="EVID-COLLISION")
        with patch(
            "registration_validation.models._new_evidence_code",
            side_effect=(existing.code, "EVID-UNIQUE-SECOND-TRY"),
        ):
            created = self.make_evidence()

        self.assertEqual(created.code, "EVID-UNIQUE-SECOND-TRY")
        self.assertEqual(Evidence.objects.filter(code=existing.code).count(), 1)

    def test_existing_evidence_code_is_preserved(self):
        evidence = self.make_evidence(code="LEGACY-EVIDENCE-CODE")

        evidence.file_link = "evidence/legacy-updated"
        evidence.save()
        evidence.refresh_from_db()

        self.assertEqual(evidence.code, "LEGACY-EVIDENCE-CODE")
        self.assertEqual(evidence.file_link, "evidence/legacy-updated")

    def test_evidence_code_migration_fills_only_missing_codes(self):
        existing = self.make_evidence(code="HISTORIC-VALID-CODE")
        missing = self.make_evidence()
        Evidence.objects.filter(pk=missing.pk).update(code="")
        migration = import_module(
            "registration_validation.migrations.0014_alter_evidence_code"
        )

        migration.populate_missing_evidence_codes(
            apps,
            SimpleNamespace(connection=connection),
        )

        existing.refresh_from_db()
        missing.refresh_from_db()
        self.assertEqual(existing.code, "HISTORIC-VALID-CODE")
        self.assertRegex(missing.code, r"^EVID-[0-9A-F]{32}$")
        self.assertEqual(Evidence.objects.values("code").distinct().count(), 2)

    def test_evidence_create_and_update_remain_atomic_with_file_saving(self):
        activity = self.make_activity()
        evidence_count = Evidence.objects.count()
        create_form = EvidenceForm(
            data=self.evidence_form_data(
                activity,
                self.north_employee,
                code="REL-EVID-ATOMIC-CREATE",
            ),
            files=self.evidence_files(),
        )
        self.assertTrue(create_form.is_valid(), create_form.errors)

        create_view = EvidenceCreateView()
        create_view.request = RequestFactory().post("/")
        create_view.object = None
        with patch(
            "registration_validation.views.save_evidence_files",
            side_effect=OSError("Falló la persistencia del archivo"),
        ):
            with self.assertRaises(OSError):
                create_view.form_valid(create_form)

        self.assertEqual(Evidence.objects.count(), evidence_count)

        existing = self.make_evidence(
            activity,
            self.north_employee,
            code="REL-EVID-ATOMIC-UPDATE",
        )
        update_data = self.evidence_form_data(
            activity,
            self.north_employee,
            code=existing.code,
        )
        update_data["file_link"] = "evidence/updated"
        update_form = EvidenceForm(
            data=update_data,
            files=self.evidence_files(),
            instance=existing,
        )
        self.assertTrue(update_form.is_valid(), update_form.errors)

        update_view = EvidenceUpdateView()
        update_view.request = RequestFactory().post("/")
        update_view.object = existing
        with patch(
            "registration_validation.views.save_evidence_files",
            side_effect=OSError("Falló la persistencia del archivo"),
        ):
            with self.assertRaises(OSError):
                update_view.form_valid(update_form)

        existing.refresh_from_db()
        self.assertEqual(existing.file_link, "evidence/test")

    def test_evidence_update_cannot_move_across_goals_but_can_move_within_goal(self):
        activity = self.make_activity()
        same_goal_activity = self.make_activity(
            goal=self.north_goal_other,
            author=self.north_employee_other,
        )
        evidence = self.make_evidence(
            activity,
            self.north_employee,
            code="REL-EVID-MOVE",
        )

        # A move between different goals is rejected to avoid leaving the
        # previous goal's monitoring indicator stale.
        evidence.activity = same_goal_activity
        evidence.author = self.north_employee_other
        with self.assertRaises(ValidationError):
            evidence.save()

        second_north_activity = self.make_activity(
            goal=self.north_goal,
            author=self.north_employee,
            contact="Segundo contacto",
        )
        evidence.activity = second_north_activity
        evidence.save()
        evidence.refresh_from_db()
        self.assertEqual(evidence.activity_id, second_north_activity.pk)

    def test_validation_allows_other_verifier_same_delegation_and_rejects_cross(self):
        evidence = self.make_evidence()
        valid = Validation(
            evidence=evidence,
            verifier=self.north_employee_other,
            decision="Approved",
            date=timezone.now(),
            result="Approved",
        )
        valid.full_clean()
        valid.save()

        with self.assertRaises(ValidationError) as context:
            Validation.objects.create(
                evidence=evidence,
                verifier=self.south_employee,
                decision="Approved",
                date=timezone.now(),
                result="Approved",
            )
        self.assertIn("verifier", context.exception.message_dict)

    def test_validation_form_validates_creation_and_relationship_updates(self):
        evidence = self.make_evidence()
        allowed_form = ValidationForm(
            data=self.validation_form_data(
                evidence,
                self.north_employee_other,
            )
        )
        self.assertTrue(allowed_form.is_valid(), allowed_form.errors)

        invalid_form = ValidationForm(
            data=self.validation_form_data(
                evidence,
                self.south_employee,
                version=2,
            )
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("verifier", invalid_form.errors)

        existing = self.make_validation(
            evidence=evidence,
            verifier=self.north_employee,
            version=3,
        )
        invalid_update = ValidationForm(
            data=self.validation_form_data(
                evidence,
                self.south_employee,
                version=3,
            ),
            instance=existing,
        )
        self.assertFalse(invalid_update.is_valid())
        self.assertIn("verifier", invalid_update.errors)

    def test_validation_decision_selector_preserves_historical_values(self):
        evidence = self.make_evidence()
        create_data = self.validation_form_data(
            evidence,
            self.north_employee,
        )
        create_data["decision"] = "Observed"
        create_form = ValidationForm(data=create_data)
        self.assertIn("<select", str(create_form["decision"]))
        self.assertEqual(
            dict(create_form.fields["decision"].widget.choices)["Approved"],
            "Aprobada",
        )
        self.assertEqual(
            create_form.fields["result"].widget.input_type,
            "text",
        )
        self.assertTrue(create_form.is_valid(), create_form.errors)

        legacy_label_data = self.validation_form_data(
            evidence,
            self.north_employee,
        )
        legacy_label_data["decision"] = "Aprobada"
        legacy_label_form = ValidationForm(data=legacy_label_data)
        self.assertTrue(legacy_label_form.is_valid(), legacy_label_form.errors)
        self.assertEqual(
            legacy_label_form.cleaned_data["decision"],
            "Approved",
        )

        invalid_form = ValidationForm(
            data=dict(create_data, decision="Unrecognized"),
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("decision", invalid_form.errors)

        existing = self.make_validation(evidence=evidence)
        existing.decision = "Historical decision"
        existing.save(update_fields=("decision",))
        update_data = self.validation_form_data(
            evidence,
            self.north_employee,
            version=existing.version,
        )
        update_data["decision"] = existing.decision
        update_form = ValidationForm(data=update_data, instance=existing)
        self.assertIn(
            "Historical decision",
            dict(update_form.fields["decision"].widget.choices),
        )
        self.assertTrue(update_form.is_valid(), update_form.errors)

    def test_validation_update_cannot_move_across_goals(self):
        north_evidence = self.make_evidence(code="REL-EVID-NORTH-VAL")
        south_activity = self.make_activity(
            goal=self.south_goal,
            author=self.south_employee,
        )
        south_evidence = self.make_evidence(
            activity=south_activity,
            author=self.south_employee,
            code="REL-EVID-SOUTH-VAL",
        )
        validation = self.make_validation(evidence=north_evidence)
        validation.evidence = south_evidence
        validation.verifier = self.south_employee

        with self.assertRaises(ValidationError):
            validation.save()

    def test_admin_forms_enforce_the_model_relationship_rules(self):
        user = get_user_model().objects.create_user(
            username="registro-admin-relaciones",
            password="test-password",
        )
        user.is_superuser = True
        request = RequestFactory().get("/admin/")
        request.user = user

        activity = self.make_activity()
        activity_form_class = admin.site._registry[
            Activity
        ].get_form(request, obj=activity)
        activity_form = activity_form_class(
            data={
                "goal": self.north_goal.pk,
                "author": self.north_employee_other.pk,
                "activity_type": "",
                "date": "2026-06-01",
                "request_problem": "Solicitud",
                "action": "Acción",
                "contact": "Contacto",
                "phone": "555",
                "status": "Pending",
            },
            instance=activity,
        )
        self.assertFalse(activity_form.is_valid())
        self.assertIn("author", activity_form.errors)

        evidence = self.make_evidence()
        evidence_form_class = admin.site._registry[
            Evidence
        ].get_form(request, obj=evidence)
        evidence_form = evidence_form_class(
            data={
                "code": evidence.code,
                "activity": evidence.activity_id,
                "author": self.south_employee.pk,
                "file_link": "evidence/admin",
                "date": "2026-06-01T10:00",
                "metadata": "{}",
                "review_status": "Pending",
            },
            instance=evidence,
        )
        self.assertFalse(evidence_form.is_valid())
        self.assertIn("author", evidence_form.errors)

        validation = self.make_validation(evidence=evidence)
        validation_form_class = admin.site._registry[
            Validation
        ].get_form(request, obj=validation)
        validation_form = validation_form_class(
            data={
                "evidence": evidence.pk,
                "verifier": self.south_employee.pk,
                "decision": "Approved",
                "date": "2026-06-01T10:00",
                "observation": "",
                "result": "Approved",
                "version": validation.version,
            },
            instance=validation,
        )
        self.assertFalse(validation_form.is_valid())
        self.assertIn("verifier", validation_form.errors)

    def test_multi_delegation_forms_keep_authorized_options_and_active_scope(self):
        self.make_activity()
        south_activity = self.make_activity(
            goal=self.south_goal,
            author=self.south_employee,
        )
        south_evidence = self.make_evidence(
            activity=south_activity,
            author=self.south_employee,
            code="REL-EVID-MULTI-SOUTH",
        )
        user = get_user_model().objects.create_user(
            username="registro-multi-delegacion",
            password="test-password",
        )
        profile = UserProfile.objects.create(
            user=user,
            employee_code="REL-MULTI",
            delegation=self.north,
        )
        profile.authorized_delegations.add(self.north, self.south)
        permissions = Permission.objects.filter(
            content_type__app_label="registration_validation",
            codename__in=("add_evidence", "add_validation"),
        )
        user.user_permissions.add(*permissions)

        evidence_form = EvidenceForm(user=user)
        self.assertTrue(
            evidence_form.fields["activity"].queryset.filter(
                goal__employee__delegation=self.north
            ).exists()
        )
        self.assertTrue(
            evidence_form.fields["activity"].queryset.filter(
                goal__employee__delegation=self.south
            ).exists()
        )
        self.assertIn(
            self.south_employee.pk,
            evidence_form.fields["author"].queryset.values_list(
                "pk",
                flat=True,
            ),
        )
        cross_delegation_form = EvidenceForm(
            data=self.evidence_form_data(
                south_activity,
                self.north_employee,
                code="REL-FORM-MULTI-CROSS",
            ),
            files=self.evidence_files(),
            user=user,
        )
        self.assertFalse(cross_delegation_form.is_valid())
        self.assertIn("author", cross_delegation_form.errors)

        multi_validation_form = ValidationForm(user=user)
        self.assertTrue(
            multi_validation_form.fields["evidence"].queryset.filter(
                pk=south_evidence.pk
            ).exists()
        )
        cross_validation_form = ValidationForm(
            data=self.validation_form_data(
                south_evidence,
                self.north_employee,
                version=20,
            ),
            user=user,
        )
        self.assertFalse(cross_validation_form.is_valid())
        self.assertIn("verifier", cross_validation_form.errors)

        user.sgr_active_delegation_id = self.north.pk
        active_evidence_form = EvidenceForm(user=user)
        self.assertFalse(
            active_evidence_form.fields["activity"].queryset.filter(
                goal__employee__delegation=self.south
            ).exists()
        )
        self.assertFalse(
            active_evidence_form.fields["author"].queryset.filter(
                delegation=self.south
            ).exists()
        )

        validation_form = ValidationForm(user=user)
        self.assertFalse(
            validation_form.fields["evidence"].queryset.filter(
                activity__goal__employee__delegation=self.south
            ).exists()
        )
