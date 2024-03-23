"""
Tests to validate iripau.threading module
"""

import pytest
import random
import threading

from time import sleep
from itertools import groupby
from multiprocessing.dummy import Pool

from iripau.threading import AsyncResult
from iripau.threading import MultiDequeuer
from iripau.threading import synchronized
from iripau.threading import cached


class TestAsyncResult:

    def test_success(self):
        def some_function(arg1, arg2=None):
            sleep(3)
            return arg1 + arg2

        result = AsyncResult(some_function, 1, 2)
        result.wait(1)
        assert not result.ready()
        with pytest.raises(ValueError):
            result.successful()
        with pytest.raises(TimeoutError):
            result.get(1)
        assert 3 == result.get()
        assert result.ready()
        assert result.successful()

    def test_success_context(self):
        def some_function(arg1, arg2=None):
            sleep(4)
            return arg1 + arg2

        with AsyncResult(some_function, 1, 2) as result:
            result.wait(1)
            assert not result.ready()
            with pytest.raises(ValueError):
                result.successful()
            with pytest.raises(TimeoutError):
                result.get(1)
        assert result.ready()
        assert 3 == result.get()
        assert result.successful()

    def test_exception(self):
        def some_function(arg1, arg2=None):
            sleep(3)
            assert False

        result = AsyncResult(some_function, 1)
        result.wait(1)
        assert not result.ready()
        with pytest.raises(ValueError):
            result.successful()
        with pytest.raises(TimeoutError):
            result.get(1)
        with pytest.raises(AssertionError):
            result.get()
        assert result.ready()
        assert not result.successful()


class TestMultiDequeuer:

    def test_consume_immediately(self):
        num_products = 10
        num_threads = num_products
        data = []

        def consumer(products):
            data.append(products)

        md = MultiDequeuer(consumer, collection_type=set)

        with Pool(num_threads) as pool:
            results = []
            for i in range(num_products):
                sleep(0.1)
                results.append(pool.apply_async(md.put, (i,)))
            [result.get() for result in results]

        assert [{0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}, {8}, {9}] == data

    def test_consume_after_time(self):
        num_products = 10
        num_threads = num_products
        data = []

        def consumer(products):
            data.append(products)

        md = MultiDequeuer(consumer, 0.7, collection_type=set)

        with Pool(num_threads) as pool:
            results = []
            for i in range(num_products):
                sleep(0.1)
                results.append(pool.apply_async(md.put, (i,)))
            [result.get() for result in results]

        assert [{0, 1, 2, 3, 4, 5, 6}, {7, 8, 9}] == data

    def test_consume_when_count_reached(self):
        num_products = 10
        num_threads = num_products
        data = []

        def consumer(products):
            data.append(products)

        md = MultiDequeuer(consumer, None, 5, set)

        with Pool(num_threads) as pool:
            results = []
            for i in range(num_products):
                sleep(0.1)
                results.append(pool.apply_async(md.put, (i,)))
            [result.get() for result in results]

        assert [{0, 1, 2, 3, 4}, {5, 6, 7, 8, 9}] == data

    def test_consume_mixed(self):
        num_products = 10
        num_threads = num_products
        data = []

        def consumer(products):
            data.append(products)

        md = MultiDequeuer(consumer, 0.5, 4, set)

        with Pool(num_threads) as pool:
            results = []
            for i in range(num_products):
                sleep(0.1)
                results.append(pool.apply_async(md.put, (i,)))
            [result.get() for result in results]

        assert [{0, 1, 2, 3}, {4, 5, 6, 7}, {8, 9}] == data


class TestThreading:

    @pytest.mark.parametrize("cases", ["no_parenthesis", "empty_parenthesis", "parenthesis"])
    def test_synchronized(self, cases):
        num_inserts = 500
        num_threads = 500
        data = []

        match cases:
            case "no_parenthesis":
                decorator = synchronized
            case "empty_parenthesis":
                decorator = synchronized()
            case "parenthesis":
                decorator = synchronized(threading.BoundedSemaphore())

        @decorator
        def f(arg):
            for i in range(num_inserts):
                data.append(arg)

        with Pool(num_threads) as pool:
            results = [pool.apply_async(f, (i,)) for i in range(num_threads)]
            [result.get() for result in results]

        assert len(list(groupby(data))) == num_threads
        assert len(data) == num_threads * num_inserts

    @pytest.mark.parametrize("shifted", [True, False], ids=["no_parenthesis", "parenthesis"])
    def test_cached(self, shifted):
        num_inserts = 50
        num_repeats = 40
        num_threads = num_inserts * num_repeats
        data = []

        decorator = cached if shifted else cached()

        @decorator
        def f(arg):
            sleep(random.random())
            data.append(arg)
            return len(data)

        expected_data = list(range(num_inserts))
        expected_values = [
            i + 1
            for i in range(num_inserts)
            for j in range(num_repeats)
        ]

        with Pool(num_threads) as pool:
            results = [
                pool.apply_async(f, (i,))
                for i in expected_data
                for j in range(num_repeats)
            ]
            values = [result.get() for result in results]

        assert expected_values != values
        assert expected_data != data

        assert expected_values == sorted(values)
        assert expected_data == sorted(data)

    def test_cached_synchronized(self):
        num_inserts = 25
        num_repeats = 40
        num_threads = num_inserts * num_repeats
        data = []

        @cached(synchronized=True)
        def f(arg):
            sleep(random.random())
            data.append(arg)
            return len(data)

        expected_data = list(range(num_inserts))
        expected_values = [
            i + 1
            for i in range(num_inserts)
            for j in range(num_repeats)
        ]

        with Pool(num_threads) as pool:
            results = [
                pool.apply_async(f, (i,))
                for i in expected_data
                for j in range(num_repeats)
            ]
            values = [result.get() for result in results]

        assert expected_values == values
        assert expected_data == data
