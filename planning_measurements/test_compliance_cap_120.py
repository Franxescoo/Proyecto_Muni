"""Regresión: límite nuevo de 120 % y preservación de períodos históricos."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from .forms import PeriodForm
from .models import Period


class PeriodComplianceCap120Tests(TestCase):
    BASE_THRESHOLDS = "Verde: 100, Amarillo: 80, Rojo: 60"

    def data(self, **changes):
        values = {
            "start_date": "2026-11-02",
            "end_date": "2026-11-30",
            "computable_days": "",
            "status": Period.Status.ACTIVE,
            "thresholds": self.BASE_THRESHOLDS,
            "parameters_version": "v1",
            "compliance_cap": "120",
        }
        values.update(changes)
        return values

    def historical_period(self, thresholds=None):
        return Period.objects.create(
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 30),
            computable_days=20,
            status=Period.Status.ACTIVE,
            thresholds=thresholds or self.BASE_THRESHOLDS + ", Tope: 150.00",
            parameters_version="v1",
        )

    def test_default_for_new_period_is_120(self):
        self.assertEqual(PeriodForm().fields["compliance_cap"].initial, Decimal("120"))
        form = PeriodForm(self.data(compliance_cap=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn("Tope: 120.00", form.cleaned_data["thresholds"])

    def test_exactly_120_is_valid(self):
        form = PeriodForm(self.data(compliance_cap="120"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_new_period_rejects_121(self):
        form = PeriodForm(self.data(compliance_cap="121"))
        self.assertFalse(form.is_valid())
        self.assertIn("compliance_cap", form.errors)

    def test_new_period_rejects_150(self):
        form = PeriodForm(self.data(compliance_cap="150"))
        self.assertFalse(form.is_valid())
        self.assertIn("compliance_cap", form.errors)

    def test_historical_cap_150_without_change_is_preserved(self):
        period = self.historical_period()
        form = PeriodForm(self.data(thresholds=period.thresholds,
                                    compliance_cap="150"), instance=period)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["thresholds"], period.thresholds)

    def test_historical_implicit_150_without_change_is_preserved(self):
        period = self.historical_period(self.BASE_THRESHOLDS)
        form = PeriodForm(self.data(compliance_cap=""), instance=period)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["thresholds"], period.thresholds)

    def test_changing_historical_thresholds_requires_new_cap_120_or_less(self):
        period = self.historical_period()
        new_thresholds = "Verde: 90, Amarillo: 75, Rojo: 60"
        forbidden = PeriodForm(self.data(thresholds=new_thresholds,
                                         compliance_cap="150"), instance=period)
        self.assertFalse(forbidden.is_valid())
        self.assertIn("compliance_cap", forbidden.errors)
        allowed = PeriodForm(self.data(thresholds=new_thresholds,
                                       compliance_cap="120"), instance=period)
        self.assertTrue(allowed.is_valid(), allowed.errors)
        self.assertIn("Tope: 120.00", allowed.cleaned_data["thresholds"])

    def test_legacy_period_allows_unrelated_date_change(self):
        period = self.historical_period()
        form = PeriodForm(self.data(thresholds=period.thresholds,
                                    compliance_cap="150",
                                    end_date="2026-12-01"), instance=period)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["thresholds"], period.thresholds)
