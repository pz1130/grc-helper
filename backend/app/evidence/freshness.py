from datetime import UTC, datetime

from app.evidence.models import EvidenceStatus


def display_status(
    status: EvidenceStatus | str,
    valid_until: datetime | None,
    now: datetime | None = None,
) -> str:
    """Calculate the live evidence status without persisting a derived value."""
    value = status.value if isinstance(status, EvidenceStatus) else status
    if value != EvidenceStatus.COLLECTED.value:
        return value
    if valid_until is None:
        return "valid"
    comparison_time = now or datetime.now(UTC)
    # PostgreSQL timestamps are timezone-aware, while callers of this pure function
    # may use naive fixture values. Treat a naive value as being in the other value's
    # timezone so a comparison never depends on Python's mixed-timezone exception.
    if valid_until.tzinfo is None and comparison_time.tzinfo is not None:
        valid_until = valid_until.replace(tzinfo=comparison_time.tzinfo)
    elif comparison_time.tzinfo is None and valid_until.tzinfo is not None:
        comparison_time = comparison_time.replace(tzinfo=valid_until.tzinfo)
    return "valid" if valid_until >= comparison_time else "expired"
