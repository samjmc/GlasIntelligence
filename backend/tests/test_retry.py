"""Unit tests for the retry mechanism."""

import pytest
from unittest.mock import MagicMock
from app.utils.retry import retry_with_backoff, RetryableAPIClient


class TestRetryDecorator:
    def test_succeeds_on_first_try(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_retries_then_succeeds(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        assert fail_twice() == "ok"
        assert call_count == 3

    def test_raises_after_max_retries(self):
        @retry_with_backoff(max_retries=2, initial_delay=0.01)
        def always_fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            always_fail()

    def test_only_retries_specified_exceptions(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01, exceptions=(ValueError,))
        def wrong_exception():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            wrong_exception()
        assert call_count == 1

    def test_on_retry_callback(self):
        callback = MagicMock()

        @retry_with_backoff(max_retries=2, initial_delay=0.01, on_retry=callback)
        def fail_once():
            if callback.call_count == 0:
                raise ValueError("first")
            return "ok"

        fail_once()
        assert callback.call_count == 1


class TestRetryableAPIClient:
    def test_call_with_retry_success(self):
        client = RetryableAPIClient(max_retries=2, initial_delay=0.01)
        result = client.call_with_retry(lambda: "ok")
        assert result == "ok"

    def test_batch_with_retry(self):
        client = RetryableAPIClient(max_retries=1, initial_delay=0.01)
        results, failures = client.call_batch_with_retry(
            [1, 2, 3],
            lambda x: x * 2,
        )
        assert results == [2, 4, 6]
        assert failures == []

    def test_batch_continues_on_failure(self):
        client = RetryableAPIClient(max_retries=0, initial_delay=0.01)

        def process(x):
            if x == 2:
                raise ValueError("bad")
            return x

        results, failures = client.call_batch_with_retry(
            [1, 2, 3], process, continue_on_failure=True
        )
        assert results == [1, 3]
        assert len(failures) == 1
        assert failures[0]["index"] == 1
