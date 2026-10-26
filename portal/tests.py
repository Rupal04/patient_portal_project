from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import AppointmentAudit, ProviderLock, User
from .services import DomainError, create, mutate


class PortalTests(TestCase):
    def setUp(self):
        ProviderLock.objects.create(pk=1)
        self.p = User.objects.create(
            name="Patient", email="p@demo.test", role="patient"
        )
        self.d = User.objects.create(
            name="Doctor", email="d@demo.test", role="provider"
        )
        self.start = timezone.now() + timedelta(days=2)

    def appointment(self):
        return create(
            {"provider_id": self.d.pk, "starts_at": self.start.isoformat()}, self.p
        )

    def test_stale_version_rejected_and_audited(self):
        a = self.appointment()
        mutate(
            a.pk,
            "reschedule",
            {"version": 1, "starts_at": (self.start + timedelta(hours=2)).isoformat()},
            self.d,
        )
        with self.assertRaises(DomainError) as ctx:
            mutate(a.pk, "confirm", {"version": 1}, self.d)
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(AppointmentAudit.objects.filter(appointment=a).count(), 2)

    def test_overlap_rejected(self):
        a = self.appointment()
        b = self.appointment()
        mutate(a.pk, "confirm", {"version": 1}, self.d)
        with self.assertRaises(DomainError) as ctx:
            mutate(b.pk, "confirm", {"version": 1}, self.d)
        self.assertEqual(ctx.exception.status, 409)
        b.refresh_from_db()
        self.assertEqual(b.status, "pending")

    def test_cancel_only_confirmed(self):
        a = self.appointment()
        with self.assertRaises(DomainError):
            mutate(a.pk, "cancel", {"version": 1}, self.p)
        mutate(a.pk, "confirm", {"version": 1}, self.d)
        mutate(a.pk, "cancel", {"version": 2}, self.p)
        a.refresh_from_db()
        self.assertEqual(a.status, "cancelled")

    def test_role_scope(self):
        a = self.appointment()
        r = self.client.get("/api/appointments/", HTTP_X_USER_ID=str(self.d.pk))
        self.assertEqual(len(r.json()["appointments"]), 1)
        other = User.objects.create(
            name="Other", email="other@demo.test", role="provider"
        )
        r = self.client.get("/api/appointments/", HTTP_X_USER_ID=str(other.pk))
        self.assertEqual(r.json()["appointments"], [])
