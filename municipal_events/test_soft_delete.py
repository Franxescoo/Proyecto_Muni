from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from municipal_events.tests import CampaignWorkflowTests
from municipal_events.models import Beneficiary, Enrollment, CampaignAudit, GiftDelivery


class EnrollmentSoftDeleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Reutiliza solo las fixtures existentes, no los tests de la clase de origen.
        CampaignWorkflowTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.group.permissions.add(Permission.objects.get(content_type__app_label="municipal_events", codename="change_enrollment"))
        self.client.force_login(self.user1)
        self.beneficiary = Beneficiary.objects.create(name="Niño", rut="123456785", birth_date="2017-01-01")
        self.enrollment = Enrollment.objects.create(campaign=self.campaign, beneficiary=self.beneficiary,
            attention=self.a1, delegation=self.d1, created_by=self.user1)

    def test_deactivate_restore_keeps_same_row_and_history(self):
        endpoint=reverse("municipal_events:enrollment_deactivate", args=[self.enrollment.pk])
        self.assertEqual(self.client.post(endpoint, {"reason":"Registro duplicado en revisión"}).status_code,302)
        self.enrollment.refresh_from_db()
        self.assertIsNotNone(self.enrollment.deleted_at)
        self.assertEqual(Enrollment.objects.count(),1)
        self.assertEqual(CampaignAudit.objects.filter(enrollment=self.enrollment, action="DESACTIVADA").count(),1)
        self.assertEqual(self.client.post(reverse("municipal_events:enrollment_reactivate", args=[self.enrollment.pk]), {"reason":"Error subsanado"}).status_code,302)
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.deleted_at)
        self.assertEqual(Enrollment.objects.count(),1)

    def test_permission_required_for_deactivation(self):
        from django.contrib.auth.models import User
        user=User.objects.create_user("sin_permiso_eliminar", password="test-password")
        self.client.force_login(user)
        r=self.client.post(reverse("municipal_events:enrollment_deactivate", args=[self.enrollment.pk]),
                           {"reason":"Intento no autorizado"})
        self.assertEqual(r.status_code,403)
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.deleted_at)

    def test_cannot_deactivate_delivery(self):
        self.enrollment.status="APPROVED"
        self.enrollment.save()
        GiftDelivery.objects.create(enrollment=self.enrollment, delivered_by=self.user1)
        self.assertEqual(self.client.post(reverse("municipal_events:enrollment_deactivate", args=[self.enrollment.pk]), {"reason":"No procede"}).status_code,403)
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.deleted_at)

    def test_duplicate_rut_still_blocked_in_same_campaign(self):
        self.enrollment.deleted_at=timezone.now()
        self.enrollment.save()
        r = self.client.post(reverse("municipal_events:enrollment_create", args=[self.campaign.pk]), {
            "attention": self.a1.pk, "rut": self.beneficiary.rut,
            "name": self.beneficiary.name, "birth_date": "2017-01-01","sex": "M",})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,"desactivada")
        self.assertEqual(Enrollment.objects.count(),1)

    def test_not_visible_by_default_when_inactive(self):
        self.enrollment.deleted_at=timezone.now()
        self.enrollment.save()
        self.assertNotContains(self.client.get(reverse("municipal_events:enrollment_list")), "Niño")
        self.assertContains(self.client.get(reverse("municipal_events:enrollment_list")+"?record_state=inactive"), "Niño")
