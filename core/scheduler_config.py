"""
◑ Ephe – The run knobs of the schedule (wave I7)
core/scheduler_config.py

Four values that stood as literals in `core/scheduler.py` — the catch-up window of a
missed run, how many runs stay stored, how many runs the surface shows, how many runs
of the same job run at once — are controls in the registry (core/settings_schema.py
::cron). This module holds the readers; the scheduler stays a scheduler.

Default by default exactly as the behavior was before. Not built, because there is no
reader for it: a time limit per run (no `wait_for` in `_run_task`), retries after an
error (the error is only noted), and switching the presets on or off
(`SCHEDULE_PRESETS` is still delivered unchanged).
"""
from __future__ import annotations


def misfire_grace_seconds() -> int:
    """Tolerance for a run that was missed because of a restart."""
    from core.settings_schema import deep_number

    return int(deep_number("cron.misfire_grace_minutes")) * 60


def misfire_grace_setting() -> int:
    """The grace as APScheduler takes it: `misfire_grace_time` validates as None or a
    positive integer, while the register's 0 means "never catch up". None would be the
    opposite of that (no limit), so 0 becomes a one second grace — a run time that
    slipped at all is dropped, a run time that is on time still runs.
    """
    return max(1, misfire_grace_seconds())


def history_keep() -> int:
    """How many runs are kept — in memory and in the file."""
    from core.settings_schema import deep_number

    return int(deep_number("cron.history_keep"))


def history_rows() -> int:
    """How many runs the surface shows at once."""
    from core.settings_schema import deep_number

    return int(deep_number("cron.history_rows"))


def max_parallel_jobs() -> int:
    """Concurrent runs of the same job (APScheduler `max_instances`)."""
    from core.settings_schema import deep_number

    return int(deep_number("cron.max_parallel_jobs"))
