# Patient Portal — Django take-home assignment

## Run locally

Python 3.10+ recommended.

```bash
python -m pip install -r requirements.txt
python manage.py migrate --run-syncdb
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/. Switch between demo users at the top.

## Features

- Patient: list, request (pending), cancel confirmed appointments.
- Provider: list assigned appointments, confirm pending, reschedule pending/confirmed.
- Audit trail: actor, action, full before/after snapshots, timestamp.
- Optimistic version check: stale browser requests get HTTP 409; nothing is silently overwritten.
- Confirmed appointment overlap prevention: half-open time intervals `[start, end)` with 30-minute duration.
- Background notification: on-commit daemon thread logs what would be sent. No real email.

## Concurrency design and limits

SQLite serializes writes database-wide. The transaction first updates a dedicated singleton `ProviderLock` row, acquiring the SQLite writer lock **before** reading appointment state or checking overlaps. Competing confirmations therefore cannot both pass the overlap check: the second waits or gets a retryable HTTP 503 (SQLite busy). It must retry, at which point it sees the first confirmed appointment and receives HTTP 409. This deliberately trades write throughput for simple, correct local behavior. All writes to confirmed appointments must go through this service, not raw model updates. For production PostgreSQL, replace the global lock with per-provider locking and preferably an exclusion constraint on `(provider_id, tstzrange(starts_at, ends_at)) WHERE status='confirmed'`, which enforces non-overlap at the database level even outside the service.

A reschedule of a pending appointment keeps it pending. A reschedule of a confirmed appointment keeps it confirmed, after overlap validation. Cancelled appointments are terminal. The patient has no Confirm button, consistent with the assignment baseline (provider confirms); a stale patient Cancel is rejected if the provider rescheduled first.

The notification thread is best-effort and not durable; a process crash after commit could lose it. Production should use a transactional outbox plus worker, retries and idempotency. No authentication/CSRF protections are included because this is explicitly a demo with a role switcher; **never deploy publicly as-is**. Date/time is submitted as timezone-aware ISO-8601 and displayed in browser local time.

## Tests

```bash
python manage.py test
```

## Demo walkthrough

1. Switch to a patient; create an appointment and see pending status.
2. Switch to provider; confirm; inspect History and server log.
3. Switch to patient; cancel confirmed appointment.
4. Create two pending requests at the same time for one provider; confirm one, then attempt the other: conflict.
5. Open two tabs on one appointment; reschedule in one tab, attempt action in stale tab: HTTP 409.

## AI usage disclosure

This implementation was generated with AI assistance based on the user's handwritten design and the provided assignment. Include the conversation transcript in the submission if required by the evaluator.
