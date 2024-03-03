"""
Tests to validate iripau.functools module
"""

import pytest
import operator
import multiprocessing

from time import sleep

from iripau.functools import wait_for
from iripau.functools import retry
from iripau.functools import globalize


class TestFunctools:

    @pytest.mark.parametrize("timeout", [False, True], ids=["successful", "timed_out"])
    @pytest.mark.parametrize("outcome", [False, True])
    def test_wait_for(self, outcome, timeout):
        data = [0]

        operation = operator.gt if outcome else operator.le

        def condition(arg1, arg2):
            sleep(0.4)
            data[0] = data[0] + 1
            return operation(data[0], 3)

        if timeout:
            with pytest.raises(TimeoutError):
                wait_for(
                    condition, "Arg1", "Arg2",
                    _timeout=1,
                    _outcome=outcome,
                    _poll_time=0.5
                )
        else:
            wait_for(
                condition, "Arg1", "Arg2",
                _timeout=2,
                _outcome=outcome,
                _poll_time=0.5
            )

    def test_wait_for_with_stop_condition(self):
        data = [0]

        def condition(arg1, arg2):
            data[0] = data[0] + 1
            return data[0] > 5

        def stop_condition():
            return data[0] > 3

        with pytest.raises(InterruptedError):
            wait_for(
                condition, "Arg1", "Arg2",
                _poll_time=0.5,
                _stop_condition=stop_condition
            )

        assert data[0] == 4

    @pytest.mark.parametrize("use_yield", [False, True], ids=["no_yield", "yield"])
    @pytest.mark.parametrize("success", [True, False], ids=["successful", "unsuccessful"])
    def test_retry(self, success, use_yield):
        data = [0]
        return_value = "SomeReturnValue"

        def regular_function():
            data[0] = data[0] + 1
            assert data[0] >= 3
            return return_value

        def generator_function():
            data[0] = data[0] + 1
            yield
            assert data[0] >= 3
            return return_value

        function = generator_function if use_yield else regular_function
        function = retry(4 if success else 2, AssertionError)(function)

        if success:
            assert return_value == function()
        else:
            with pytest.raises(AssertionError):
                function()

    def test_retry_failure_before_yield(self):
        data = [0]

        @retry(1, AssertionError)
        def function():
            assert False
            yield
            data[0] = 1

        with pytest.raises(AssertionError):
            function()

        assert data[0] == 0

    @pytest.mark.parametrize("fulfilled", [True, False], ids=["fulfilled", "not_fulfilled"])
    def test_retry_with_condition(self, fulfilled):
        data = [0]
        error_message = "expected message" if fulfilled else "wrong message"

        def condition(exception):
            return "expected" in str(exception)

        @retry(2, AssertionError, condition)
        def function():
            data[0] = data[0] + 1
            assert False, error_message

        with pytest.raises(AssertionError):
            function()

        expected_tries = 2 if fulfilled else 1
        assert data[0] == expected_tries

    def test_globalize(self):

        @globalize
        def local_function(x):
            return x + 1

        with multiprocessing.Pool(processes=1) as pool:
            results = pool.map(local_function, [0])

        assert results == [1]
