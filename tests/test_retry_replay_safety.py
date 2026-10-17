"""W3-46: the retry boundary — which failing calls may be replayed.

``RetryPolicy.may_replay`` is the single decision, and ``stream_with_retry``
decides through it. A call is replayed only while it has delivered nothing
(``emitted`` False), an attempt is left, and the failure is transient
(``core/provider_errors``).

What is safe: a pure model call that failed before delivering a chunk — a replay
repeats only its compute. What is not: a chunk already sent to the consumer (it
would arrive twice), an exhausted attempt budget, and a caller error that answers
the same way on every attempt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core.chat_stream import RetryPolicy, stream_with_retry

TRANSIENT = ConnectionError("connection refused")
CALLER_ERROR = RuntimeError("model 'x' not found locally")
POLICY = RetryPolicy(max_attempts=3, base_delay=0.0)


async def _no_sleep(_delay: float) -> None:
    return None


def ok_stream(*chunks):
    async def _gen():
        for chunk in chunks:
            yield {"message": {"content": chunk}}

    return _gen


def failing_stream(error: BaseException, *, after: str | None = None):
    """A stream that optionally delivers one chunk, then raises."""

    async def _gen():
        if after is not None:
            yield {"message": {"content": after}}
        raise error

    return _gen


@dataclass(frozen=True)
class RecordingPolicy(RetryPolicy):
    """A policy that answers from a fixed verdict and records what the loop asked."""

    allowed: bool = True
    seen: list = field(default_factory=list)

    def may_replay(self, error, *, attempt, emitted):
        self.seen.append((attempt, emitted))
        return self.allowed

    def delay_for(self, attempt):
        return 0.0


# The decision table.


def test_a_transient_failure_before_any_output_may_be_replayed():
    assert POLICY.may_replay(TRANSIENT, attempt=1, emitted=False) is True


def test_a_chunk_already_delivered_blocks_replay():
    # The same transient failure after the first chunk: a replay would send the
    # chunk to the consumer a second time.
    assert POLICY.may_replay(TRANSIENT, attempt=1, emitted=True) is False


def test_an_exhausted_budget_blocks_replay():
    assert POLICY.may_replay(TRANSIENT, attempt=POLICY.max_attempts, emitted=False) is False


def test_the_last_allowed_attempt_is_not_yet_exhausted():
    assert POLICY.may_replay(TRANSIENT, attempt=POLICY.max_attempts - 1, emitted=False) is True


def test_a_caller_error_blocks_replay():
    assert POLICY.may_replay(CALLER_ERROR, attempt=1, emitted=False) is False


def test_a_single_attempt_policy_never_replays():
    once = RetryPolicy(max_attempts=1, base_delay=0.0)
    assert once.may_replay(TRANSIENT, attempt=1, emitted=False) is False


def test_every_reason_to_replay_can_stand_alone():
    # emitted, budget, and transience each independently block the replay.
    assert POLICY.may_replay(TRANSIENT, attempt=1, emitted=False) is True
    assert POLICY.may_replay(TRANSIENT, attempt=1, emitted=True) is False
    assert POLICY.may_replay(TRANSIENT, attempt=99, emitted=False) is False
    assert POLICY.may_replay(CALLER_ERROR, attempt=1, emitted=False) is False


# The loop decides through the policy.


async def test_stream_with_retry_asks_the_policy_and_obeys_a_denial():
    recorder = RecordingPolicy(allowed=False)
    attempts = {"n": 0}

    def open_stream():
        attempts["n"] += 1
        return failing_stream(TRANSIENT)()

    with pytest.raises(ConnectionError):
        async for _ in stream_with_retry(open_stream, policy=recorder, sleep=_no_sleep):
            pass
    assert attempts["n"] == 1
    assert recorder.seen == [(1, False)]


async def test_stream_with_retry_replays_when_the_policy_allows_it():
    recorder = RecordingPolicy(allowed=True)
    attempts = {"n": 0}

    def open_stream():
        attempts["n"] += 1
        if attempts["n"] < 2:
            return failing_stream(TRANSIENT)()
        return ok_stream("done")()

    chunks = [
        chunk
        async for chunk in stream_with_retry(open_stream, policy=recorder, sleep=_no_sleep)
    ]
    assert [c["message"]["content"] for c in chunks] == ["done"]
    assert recorder.seen == [(1, False)]


async def test_the_loop_stops_asking_once_the_budget_is_spent():
    # With a real policy the loop replays until max_attempts, then raises: the
    # call is attempted exactly max_attempts times, never one more.
    policy = RetryPolicy(max_attempts=2, base_delay=0.0)
    attempts = {"n": 0}

    def open_stream():
        attempts["n"] += 1
        return failing_stream(TRANSIENT)()

    with pytest.raises(ConnectionError):
        async for _ in stream_with_retry(open_stream, policy=policy, sleep=_no_sleep):
            pass
    assert attempts["n"] == 2


# The first delivered chunk is the commit point.


async def test_a_chunk_commits_the_call_even_when_an_attempt_is_left():
    policy = RetryPolicy(max_attempts=3, base_delay=0.0)
    attempts = {"n": 0}

    def open_stream():
        attempts["n"] += 1
        return failing_stream(TRANSIENT, after="partial")()

    with pytest.raises(ConnectionError):
        async for _ in stream_with_retry(open_stream, policy=policy, sleep=_no_sleep):
            pass
    assert attempts["n"] == 1
