"""
Generic and stand-alone threading utilities.
"""

import sys
import threading

from typing import Any, Callable, Collection, Type
from functools import wraps, _make_key as make_key
from collections import deque


class AsyncResult(threading.Thread):
    """ Implementation of the :class:`multiprocessing.pool.AsyncResult` class but
        spawning a new thread to execute the target ``function`` instead of using
        a Process or Thread Pool.

        Args:
            function: Callable to run in a thnread.
            *args: Will be passed to ``function``.
            **kwargs: Will be passed to ``function``.


        Example:
            Start multiplying two matrices, do other things, and then print the
            multiplication result::

                from time import sleep
                from random import randint
                from operator import mul


                def slow_matmul(a, b):
                    return [[sum(map(mul, a_row, b_col)) for b_col in zip(*b)] for a_row in a]


                a = [[randint(0, 100) for _ in range(1000)] for _ in range(1000)]
                b = [[randint(0, 100) for _ in range(1000)] for _ in range(1000)]
                result = AsyncResult(slow_matmul, a, b)

                print("Processing...")
                while not result.ready():
                    sleep(5)
                    print("Still processing...")

                print(*result.get(timeout=900), sep="\\n")

        Example:
            Perform several matrix multiplications at once and print the results::

                from random import randint


                def random_mat_mul():
                    a = [[randint(0, 100) for _ in range(1000)] for _ in range(1000)]
                    b = [[randint(0, 100) for _ in range(1000)] for _ in range(1000)]
                    return slow_matmul(a, b)

                results = [AsyncResult(random_mat_mul) for _ in range(10)]
                for i, result in enumerate(results):
                    print(f"Result {i}:")
                    print(*result.get(timeout=900), sep="\\n")
    """

    def __init__(self, function: Callable[[...], Any], *args, **kwargs):
        super().__init__(
            target=function,
            args=args,
            kwargs=kwargs
        )

        self.return_value = None
        self.exc_info = None

        self.start()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.wait()

    def run(self):
        """ Run the target ``function``, store its return value or exception
            information if any.
        """
        try:
            self.return_value = self._target(*self._args, **self._kwargs)
        except:  # noqa: E722
            self.exc_info = sys.exc_info()

    def get(self, timeout: float = None) -> Any:
        """ Implementation of :meth:`multiprocessing.pool.AsyncResult.get`.

            Args:
                timeout: Maximum time in seconds to wait for the result to arrive.

            Returns:
                The target ``function`` return value when it arrives.

            Raises:
                TimeoutError: If the result does not arrive within ``timeout``..
                Exception: Whatever :class:`Exception` the target ``function``
                    raised during its execution.
        """
        self.join(timeout)
        if self.is_alive():
            raise TimeoutError("Timeout reached while joining the thread")
        if self.exc_info:
            exc_type, exc_value, traceback = self.exc_info
            raise exc_value.with_traceback(traceback)
        return self.return_value

    def wait(self, timeout: float = None):
        """ Implementation of :meth:`multiprocessing.pool.AsyncResult.wait`.

            Args:
                timeout: Maximum time to wait for the result to be available.
        """
        self.join(timeout)

    def ready(self) -> bool:
        """ Implementation of :meth:`multiprocessing.pool.AsyncResult.ready`.

            Returns:
                Whether the target ``function``  has completed
        """
        return not self.is_alive()

    def successful(self) -> bool:
        """ Implementation of :meth:`multiprocessing.pool.AsyncResult.successful`.

            Returns:
                Whether the target ``function`` completed without raising an
                exception.

            Raises:
                ValueError: If the result is not ready.
        """
        if self.is_alive():
            raise ValueError("Thread has not completed")
        try:
            self.get()
        except:  # noqa: E722
            return False
        else:
            return True


class MultiDequeuer:
    """ Implementation of the Producer-Consumer Design Pattern in which one of
        the Producer workers will act as Consumer, processing all of the
        elements that have been produced so far. Also, the workers will block
        until the elements they produced are consumed.

        This is helpful to keep the logic of processing one single element per
        worker but consuming several elements more efficiently at once, without
        the need of having a separated thread or threads for consumption.

        If there is not any advantage on consuming multiple elements at once
        compared to consuming them one by one, it is preferred to consume the
        elements in the workers, keeping the logic of blocking the workers.

        If blocking the workers is not desired, the regular Producer-Consumer
        Pattern will suffice.

        Attention:
            This class relies on the Python GIL.

        Args:
            consumer: The elements queue will be consumed by this callable, which
                will be called by one of the workers passing all of the elements
                in the queue so far. When the worker has started consuming the
                queue, a new queue will be created to handle future elements.
            time_to_consume: If this is greater than 0, the queue will be consumed
                when this time (in seconds) has passed after the first element was
                added to the queue.
            count_hint: If this is greater than 0, the queue will be consumed when
                at least this amount of elements have been added to the queue,
                ignoring ``time_to_consume``.
            collection_type: The elements queue will be cast into this type before
                it is passed to the ``consumer`` callable.
    """

    def __init__(
        self,
        consumer: Callable[[Collection[Any]], None],
        time_to_consume: int = None,
        count_hint: int = 0,
        collection_type: Type = list
    ):
        self.consume = consumer
        self.count = count_hint
        self.time = time_to_consume
        self.type = collection_type

        self.lock = threading.Lock()
        self.data = self._new_data()

    def _new_data(self):
        return (
            deque(),
            threading.Barrier(self.count, timeout=self.time),
            threading.Lock()
        )

    def put(self, product: Any):
        """ Add an element to the queue. This method is meant to be called by
            the workers. It blocks until the element is consumed.

            Args:
                product: Element to add to the queue.
        """
        data = self.data

        queue, barrier, lock = data

        queue.append(product)
        if self.count or self.time:
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass

        with self.lock:
            if self.data is data:
                self.data = self._new_data()

        with lock:
            if queue:
                products = self.type(queue)
                self.consume(products)
                queue.clear()


class FunctionCacher:
    """ Cache the return value of a callable depending on their call arguments.
        The first call will generate the cache and subsequent calls will return
        the cached value without executing the original callable.

        The instance of this class is meant to be called as if it were the
        original callable.

        The main difference from the functools.cache decorator is that the cache
        for a particular set of arguments will be generated by only one
        execution of the original callable; if more than one thread calls this
        object before the cache is generated, only one of them will actually
        execute the original callable and the rest will wait for it to finish.

        https://docs.python.org/3/library/functools.html#functools.cache
    """

    def __init__(self, function, synchronized=False, enabled=True):
        """ The callable to be cached is function.

            If enabled is False, caching will start disabled. It can be enabled
            later on.

            If synchronized is True, the original callable will be protected
            with a lock to prevent it is executed in parallel.
        """
        self.function = function
        if enabled:
            self.enable_cache(synchronized)
        else:
            self.disable_cache()
        self.lock = threading.Lock()

    def __call__(self, *args, **kwargs):
        return self.callable(*args, **kwargs)

    def enable_cache(self, synchronized=False):
        """ Enable caching if not enabled already.
            The synchronized argument is used as in the constructor.
            This method is not re-entrant nor thread-safe.
        """
        if not hasattr(self, "cache"):
            self.cache = {}
        if synchronized:
            if hasattr(self, "locks"):
                del self.locks
            self.callable = self._synced
        else:
            if not hasattr(self, "locks"):
                self.locks = {}
            self.callable = self._cached

    def disable_cache(self):
        """ Disable and delete caching if not disabled already.
            This method is not re-entrant nor thread-safe.
        """
        if hasattr(self, "cache"):
            del self.cache
        if hasattr(self, "locks"):
            del self.locks
        self.callable = self.function

    def clear_cache(self):
        """ Delete cache if caching is not disabled.
            This method is not re-entrant nor thread-safe.
        """
        if hasattr(self, "cache"):
            self.cache = {}
        if hasattr(self, "locks"):
            self.locks = {}

    def _cached(self, *args, **kwargs):
        key = make_key(args, kwargs, False)
        if key not in self.cache:
            with self.lock:
                if key not in self.locks:
                    self.locks[key] = threading.Lock()
            with self.locks[key]:
                if key not in self.cache:
                    self.cache[key] = self.function(*args, **kwargs)
        return self.cache[key]

    def _synced(self, *args, **kwargs):
        key = make_key(args, kwargs, False)
        if key not in self.cache:
            with self.lock:
                if key not in self.cache:
                    self.cache[key] = self.function(*args, **kwargs)
        return self.cache[key]


def synchronized(lock=None):
    """ Decorator to wrap a function with a lock/semaphore """
    if callable(lock):
        function, lock = lock, threading.Lock()
        shifted = True
    else:
        if lock is None:
            lock = threading.Lock()
        shifted = False

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):
            with lock:
                return function(*args, **kwargs)

        return wrapper

    return decorator(function) if shifted else decorator


def cached(synchronized=False, enabled=True):
    """ Decorator using the FunctionCacher class. """
    if callable(synchronized):
        function, synchronized = synchronized, False
        shifted = True
    else:
        shifted = False

    def decorator(function):
        return wraps(function)(FunctionCacher(function, synchronized, enabled))

    return decorator(function) if shifted else decorator
