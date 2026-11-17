"""Regresión SGR-159: cupo compartido por edición al aprobar campañas."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from municipal_events.tests import CampaignWorkflowTests
from .models import (
    Beneficiary, Campaign, CampaignAudit, Enrollment,
    EventEdition, MunicipalEvent, EventParticipation,
)


def rut_valido(base):
    digits = str(base)
    total = sum(int(x) * (2 + i % 6) for i, x in enumerate(reversed(digits)))
    rem = 11 - total % 11
    return digits + ("0" if rem == 11 else "K" if rem == 10 else str(rem))


class CampaignEditionCapacityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CampaignWorkflowTests.setUpTestData.__func__(cls)
        today = timezone.localdate()
        cls.event = MunicipalEvent.objects.create(
            name="Evento cupos SGR-159", created_by=cls.user1,
        )
        cls.edition = EventEdition.objects.create(
            event=cls.event, year=today.year, date=today, place="La Serena",
            delegation=cls.d1, responsible=cls.user1,
            participation_mode="APPLICATION", participation_capacity=1,
        )
        cls.campaign.edition = cls.edition
        cls.campaign.save(update_fields=["edition"])
        cls.other_campaign = Campaign.objects.create(
            title="Segunda campaña misma edición", year=today.year,
            attention_type=cls.attention_type, edition=cls.edition,
            organizing_delegation=cls.d1, opens_on=today-timedelta(days=1),
            closes_on=today+timedelta(days=20), status="OPEN", created_by=cls.user1,
        )

    def setUp(self):
        self.client.force_login(self.user1)

    def enroll(self, campaign, base, *, status="PENDING"):
        beneficiary = Beneficiary.objects.create(
            name=f"Niño {base}", rut=rut_valido(base),
            birth_date=date(timezone.localdate().year-8, 1, 1),
        )
        return Enrollment.objects.create(
            campaign=campaign, beneficiary=beneficiary, attention=self.a1,
            delegation=self.d1, created_by=self.user1, status=status,
        )

    def evaluate(self, item, status):
        return self.client.post(
            reverse("municipal_events:enrollment_review", args=[item.pk]),
            {"status": status, "reason": "Prueba SGR-159"},
        )

    def test_can_apply_without_consuming_capacity_and_cannot_approve_extra_across_campaigns(self):
        first = self.enroll(self.campaign, 12345678)
        extra = self.enroll(self.other_campaign, 11111111)
        self.assertEqual(self.edition.occupied_capacity(), 0)
        self.assertEqual(self.evaluate(first, "APPROVED").status_code, 302)
        self.assertEqual(self.edition.occupied_capacity(), 1)
        response = self.evaluate(extra, "APPROVED")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No quedan cupos disponibles")
        extra.refresh_from_db()
        self.assertEqual(extra.status, "PENDING")
        self.assertFalse(CampaignAudit.objects.filter(enrollment=extra, action="APPROVED").exists())

    def test_rejected_enrollment_does_not_consume_slot_and_rejecting_approved_releases_it(self):
        first = self.enroll(self.campaign, 12345678)
        second = self.enroll(self.other_campaign, 11111111)
        self.assertEqual(self.evaluate(first, "APPROVED").status_code, 302)
        self.assertEqual(self.evaluate(first, "REJECTED").status_code, 302)
        self.assertEqual(self.edition.occupied_capacity(), 0)
        self.assertEqual(self.evaluate(second, "APPROVED").status_code, 302)
        self.assertEqual(self.edition.occupied_capacity(), 1)

    def test_reapprove_same_approved_enrollment_does_not_use_extra_slot(self):
        first = self.enroll(self.campaign, 12345678)
        self.assertEqual(self.evaluate(first, "APPROVED").status_code, 302)
        self.assertEqual(self.evaluate(first, "APPROVED").status_code, 302)
        self.assertEqual(self.edition.occupied_capacity(), 1)

    def test_cannot_reactivate_approved_enrollment_when_slot_was_taken(self):
        first = self.enroll(self.campaign, 12345678, status="APPROVED")
        first.deleted_at = timezone.now()
        first.save(update_fields=["deleted_at"])
        self.assertEqual(self.edition.occupied_capacity(), 0)
        new = self.enroll(self.other_campaign, 11111111)
        self.assertEqual(self.evaluate(new, "APPROVED").status_code, 302)
        response = self.client.post(
            reverse("municipal_events:enrollment_reactivate", args=[first.pk]),
            {"reason": "Se reincorpora"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 409)
        first.refresh_from_db()
        self.assertIsNotNone(first.deleted_at)
        self.assertEqual(self.edition.occupied_capacity(), 1)

    def test_edition_cannot_lower_capacity_below_approved_enrollments(self):
        self.edition.participation_capacity = 2
        self.edition.save(update_fields=["participation_capacity"])
        first = self.enroll(self.campaign, 12345678, status="APPROVED")
        second = self.enroll(self.other_campaign, 11111111, status="APPROVED")
        self.edition.participation_capacity = 1
        with self.assertRaises(ValidationError):
            self.edition.full_clean()

    def test_unlimited_capacity_keeps_campaign_approval_unchanged(self):
        self.edition.participation_capacity = None
        self.edition.save(update_fields=["participation_capacity"])
        a = self.enroll(self.campaign, 12345678)
        b = self.enroll(self.other_campaign, 11111111)
        self.assertEqual(self.evaluate(a, "APPROVED").status_code, 302)
        self.assertEqual(self.evaluate(b, "APPROVED").status_code, 302)
        self.assertEqual(self.edition.occupied_capacity(), 2)

    def test_event_participation_and_campaign_share_edition_capacity(self):
        EventParticipation.objects.create(
            edition=self.edition, full_name="Participante de evento",
            rut=rut_valido(12345678), email="demo@example.com",
            status="ACCEPTED", created_by=self.user1,
        )
        child = self.enroll(self.campaign, 11111111)
        response = self.evaluate(child, "APPROVED")
        self.assertContains(response, "No quedan cupos disponibles")
        child.refresh_from_db()
        self.assertEqual(child.status, "PENDING")
