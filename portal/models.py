from django.db import models


class User(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=10, choices=[("patient", "Patient"), ("provider", "Provider")]
    )

    def __str__(self):
        return self.name


class Appointment(models.Model):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    patient = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="patient_appointments"
    )
    provider = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="provider_appointments"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    appointment_type = models.CharField(max_length=100, default="Consultation")
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=12,
        default=PENDING,
        choices=[
            (PENDING, "Pending"),
            (CONFIRMED, "Confirmed"),
            (CANCELLED, "Cancelled"),
        ],
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["provider", "status", "starts_at"])]


class AppointmentAudit(models.Model):
    appointment = models.ForeignKey(
        Appointment, on_delete=models.CASCADE, related_name="history"
    )
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    action = models.CharField(max_length=20)
    before = models.JSONField()
    after = models.JSONField()
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "id"]


class ProviderLock(models.Model):
    counter = models.PositiveIntegerField(default=0)
