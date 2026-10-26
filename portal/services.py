import logging
import threading
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils.dateparse import parse_datetime

from .models import Appointment, AppointmentAudit, User

log = logging.getLogger(__name__)


class DomainError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def snapshot(a):
    return {
        "starts_at": a.starts_at.isoformat(),
        "ends_at": a.ends_at.isoformat(),
        "status": a.status,
        "version": a.version,
        "provider_id": a.provider_id,
        "patient_id": a.patient_id,
    }


def serialize(a):
    return {
        "id": a.id,
        "patient_id": a.patient_id,
        "patient_name": a.patient.name,
        "provider_id": a.provider_id,
        "provider_name": a.provider.name,
        "starts_at": a.starts_at.isoformat(),
        "ends_at": a.ends_at.isoformat(),
        "status": a.status,
        "version": a.version,
        "appointment_type": a.appointment_type,
        "reason": a.reason,
    }


def dt(value):
    parsed = parse_datetime(value or "")
    if parsed is None or parsed.tzinfo is None:
        raise DomainError(
            "Use an ISO-8601 date/time with timezone, e.g. 2026-11-01T14:00:00+05:30"
        )
    return parsed


def notify_stub(email, appointment_id):
    try:
        log.warning(
            "Would send appointment confirmation for #%s to %s", appointment_id, email
        )
    except Exception:
        log.exception("Notification failed")


def schedule_notification(email, appointment_id):
    # Small exercise-only best-effort worker. Not durable; production should use a transactional outbox.
    threading.Thread(
        target=notify_stub, args=(email, appointment_id), daemon=True
    ).start()


def create(data, actor):
    if actor.role != "patient":
        raise DomainError("Only patients can request appointments", 403)
    try:
        provider = User.objects.get(pk=int(data["provider_id"]), role="provider")
    except (KeyError, ValueError, User.DoesNotExist):
        raise DomainError("Valid provider required")
    start = dt(data.get("starts_at"))
    end = start + timedelta(minutes=30)
    with transaction.atomic():
        a = Appointment.objects.create(
            patient=actor,
            provider=provider,
            starts_at=start,
            ends_at=end,
            reason=data.get("reason", ""),
            appointment_type=data.get("appointment_type", "Consultation"),
        )
        AppointmentAudit.objects.create(
            appointment=a, actor=actor, action="created", before={}, after=snapshot(a)
        )
    return a


def mutate(pk, action, data, actor):
    if action not in ("confirm", "cancel", "reschedule"):
        raise DomainError("Unknown action", 404)
    try:
        expected = int(data["version"])
    except (KeyError, ValueError, TypeError):
        raise DomainError("Expected version is required")
    # SQLite BEGIN IMMEDIATE obtains the database write lock before any reads.
    # This serializes writers, including simultaneous confirms, across processes.
    from django.db import connection

    if connection.vendor != "sqlite":
        raise DomainError("This demo concurrency strategy requires SQLite")
    connection.ensure_connection()

    # Transaction with a no-op write to a dedicated lock row before reading appointment state.
    with transaction.atomic():
        lock = ProviderLock.objects.get(pk=1)
        ProviderLock.objects.filter(pk=lock.pk).update(counter=F("counter") + 1)
        try:
            a = Appointment.objects.select_related("patient", "provider").get(pk=pk)
        except Appointment.DoesNotExist:
            raise DomainError("Appointment not found", 404)
        if a.version != expected:
            raise DomainError(
                "Appointment changed. Refresh and review the latest details before trying again.",
                409,
            )
        before = snapshot(a)
        if action == "cancel":
            if actor.pk != a.patient_id or actor.role != "patient":
                raise DomainError("Only the patient can cancel", 403)
            if a.status != "confirmed":
                raise DomainError("Only confirmed appointments can be cancelled", 409)
            a.status = "cancelled"
        else:
            if actor.pk != a.provider_id or actor.role != "provider":
                raise DomainError(
                    "Only the assigned provider can modify this appointment", 403
                )
            if a.status == "cancelled":
                raise DomainError("Cancelled appointments cannot be changed", 409)
            if action == "confirm":
                if a.status != "pending":
                    raise DomainError("Only pending appointments can be confirmed", 409)
                a.status = "confirmed"
            else:
                if a.status not in ("pending", "confirmed"):
                    raise DomainError("Cannot reschedule", 409)
                a.starts_at = dt(data.get("starts_at"))
                a.ends_at = a.starts_at + timedelta(minutes=30)
                # Rescheduling pending remains pending; confirmed remains confirmed.
            if a.status == "confirmed":
                overlaps = Appointment.objects.filter(
                    provider_id=a.provider_id,
                    status="confirmed",
                    starts_at__lt=a.ends_at,
                    ends_at__gt=a.starts_at,
                ).exclude(pk=a.pk)
                if overlaps.exists():
                    raise DomainError(
                        "Provider already has a confirmed appointment in this time slot",
                        409,
                    )
        a.version += 1
        a.save()
        AppointmentAudit.objects.create(
            appointment=a, actor=actor, action=action, before=before, after=snapshot(a)
        )
        if action == "confirm":
            transaction.on_commit(lambda: schedule_notification(a.patient.email, a.id))
    return a


from .models import ProviderLock
