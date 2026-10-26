import json

from django.db import OperationalError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .models import Appointment, User
from .services import DomainError, create, mutate, serialize


def home(request):
    return render(
        request,
        "portal/index.html",
        {"users": User.objects.all().order_by("role", "id")},
    )


def error(exc):
    return JsonResponse({"error": str(exc)}, status=getattr(exc, "status", 400))


def actor(request):
    try:
        return User.objects.get(pk=int(request.headers.get("X-User-Id", "0")))
    except (ValueError, User.DoesNotExist):
        raise DomainError("Select a valid user", 403)


def payload(request):
    try:
        return json.loads(request.body or "{}")
    except ValueError:
        raise DomainError("Invalid JSON")


@csrf_exempt
def appointments(request):
    try:
        u = actor(request)
        if request.method == "GET":
            qs = (
                Appointment.objects.select_related("patient", "provider")
                .filter(**({"patient": u} if u.role == "patient" else {"provider": u}))
                .order_by("starts_at")
            )
            return JsonResponse({"appointments": [serialize(a) for a in qs]})
        if request.method == "POST":
            return JsonResponse(serialize(create(payload(request), u)), status=201)
        return error(DomainError("Method not allowed", 405))
    except DomainError as e:
        return error(e)
    except OperationalError:
        return error(DomainError("Database busy, please retry", 503))


@csrf_exempt
def appointment_action(request, pk, action):
    if request.method != "POST":
        return error(DomainError("Method not allowed", 405))
    try:
        return JsonResponse(
            serialize(mutate(pk, action, payload(request), actor(request)))
        )
    except DomainError as e:
        return error(e)
    except OperationalError:
        return error(DomainError("Database busy, please retry", 503))


def history(request, pk):
    try:
        u = actor(request)
        a = Appointment.objects.get(pk=pk)
        if u.pk not in (a.patient_id, a.provider_id):
            raise DomainError("Not permitted", 403)
        return JsonResponse(
            {
                "history": [
                    {
                        "action": h.action,
                        "actor": h.actor.name,
                        "before": h.before,
                        "after": h.after,
                        "at": h.occurred_at.isoformat(),
                    }
                    for h in a.history.select_related("actor")
                ]
            }
        )
    except Appointment.DoesNotExist:
        return error(DomainError("Not found", 404))
    except DomainError as e:
        return error(e)
