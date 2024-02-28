"""
Function utilities
"""

import sys
import uuid
import operator

from functools import wraps
from inspect import getsource, isgeneratorfunction
from time import time, sleep


def wait_for(
    condition, *args,
    _timeout=None, _outcome=True, _poll_time=10, _stop_condition=None, **kwargs
):
    last = time()
    end = _timeout and last + _timeout
    operation = operator.not_ if _outcome else operator.truth
    while operation(condition(*args, **kwargs)):
        if _stop_condition and _stop_condition():
            message = "No reason to keep waiting since the following condition was met:\n{0}"
            raise InterruptedError(message.format(getsource(_stop_condition)))
        now = time()
        if end and now > end:
            message = "The following condition was not {0} after {1} seconds: \n{2}"
            raise TimeoutError(
                message.format(_outcome, _timeout, getsource(condition))
            )
        sleep_time = max(0, _poll_time - (now - last))
        sleep(sleep_time)
        last = now + sleep_time


def retry(tries, exceptions=Exception, retry_condition=None, backoff_time=0):
    """
        Call the decorated function until it succeeds.

        It will only retry if the expected exceptions are risen and the condition
        is fulfilled. To verify the condition is fulfilled, it will be called
        with the caught exception.

        The decorated function can have two parts divided by 'yield', in that
        case the expected exceptions will only be caught in the second part.
    """
    def decorator(function):

        @wraps(function)
        def helper(*args, **kwargs):
            yield
            return function(*args, **kwargs)

        f = function if isgeneratorfunction(function) else helper

        @wraps(function)
        def wrapper(*args, **kwargs):
            t = tries
            while t > 0:
                gen = f(*args, **kwargs)
                next(gen)
                try:
                    next(gen)
                except StopIteration as e:
                    return e.value
                except exceptions as e:
                    if retry_condition is None or retry_condition(e):
                        if t == 1:
                            raise
                        t = t - 1
                        sleep(backoff_time)
                    else:
                        raise
        return wrapper
    return decorator


def globalize(function):
    """
        Make function globally available in the module it was defined so it can
        be serialized. Useful when calling local functions with multiprocessing.
    """
    @wraps(function)
    def wrapper(*args, **kwargs):
        return function(*args, **kwargs)

    wrapper.__name__ = wrapper.__qualname__ = uuid.uuid4().hex
    setattr(sys.modules[function.__module__], wrapper.__name__, wrapper)
    return wrapper
