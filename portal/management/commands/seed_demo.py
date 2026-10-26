from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.models import Appointment, AppointmentAudit, ProviderLock, User
from portal.services import snapshot


class Command(BaseCommand):
    help = "Seed demo users and appointments"

    def handle(self, *args, **kwargs):
        ProviderLock.objects.get_or_create(pk=1)
        p, _ = User.objects.get_or_create(
            email="patient@example.com",
            defaults={"name": "Alex Patient", "role": "patient"},
        )
        p2, _ = User.objects.get_or_create(
            email="patient2@example.com",
            defaults={"name": "Sam Patient", "role": "patient"},
        )
        d, _ = User.objects.get_or_create(
            email="doctor@example.com",
            defaults={"name": "Dr Morgan", "role": "provider"},
        )
        for i, (patient, status) in enumerate(
            [(p, "pending"), (p, "confirmed"), (p2, "pending")]
        ):
            start = (timezone.now() + timedelta(days=i + 2)).replace(
                hour=14, minute=0, second=0, microsecond=0
            )
            a, created = Appointment.objects.get_or_create(
                patient=patient,
                provider=d,
                starts_at=start,
                defaults={
                    "ends_at": start + timedelta(minutes=30),
                    "status": status,
                    "reason": "Routine checkup",
                },
            )
            if created:
                AppointmentAudit.objects.create(
                    appointment=a,
                    actor=patient,
                    action="created",
                    before={},
                    after=snapshot(a),
                )
        self.stdout.write(self.style.SUCCESS("Demo ready"))
