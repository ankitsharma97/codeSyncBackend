"""
Health-check & ping endpoints.

GET /health  → detailed JSON status (DB, active rooms, uptime, etc.)
GET /ping    → bare-bones liveness probe  {"status": "pong"}
"""

import time

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone

_start_time = time.monotonic()


def _check_db():
    """Return True if the default database is reachable."""
    try:
        connection.ensure_connection()
        return True
    except Exception:
        return False


def _active_rooms_count():
    """Count rooms currently held in memory (consumers connected)."""
    try:
        from main.rooms import _rooms
        return len(_rooms)
    except Exception:
        return 0


def health(request):
    """
    Rich health-check.  Returns 200 when everything is OK, 503 when the
    database is unreachable.
    """
    db_ok = _check_db()
    uptime_seconds = round(time.monotonic() - _start_time, 2)

    payload = {
        'status': 'healthy' if db_ok else 'degraded',
        'timestamp': timezone.now().isoformat(),
        'uptime_seconds': uptime_seconds,
        'database': 'connected' if db_ok else 'unreachable',
        'active_rooms': _active_rooms_count(),
    }
    status_code = 200 if db_ok else 503
    return JsonResponse(payload, status=status_code)


def ping(request):
    """Ultra-lightweight liveness probe — no DB call."""
    return JsonResponse({'status': 'pong'})
