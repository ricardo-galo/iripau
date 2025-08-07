"""
Generic and stand-alone logging utilities that can also be used in conjunction
with :mod:`.subprocess` to log the subprocesses' ``stdout`` and ``stderr`` in
real-time, regardless of whether the subprocess raised and exception using
``check=True``, while maintaining the ability of capturing the subprocess'
output.

Example:
    Setup a logger for ``stdout``, other one for ``stderr`` and another one to
    log outside of the subprocesses. All of the loggers will write to the same
    file::

        import logging
        import tempfile


        output_file = tempfile.SpooledTemporaryFile(mode="w+t")

        normal_log_format = "%(asctime).19s - %(threadName)12.12s: %(message)s"
        output_log_format = "%(asctime).19s - %(threadName)12.12s: [%(name)s] %(message)s"

        # Setup normal log handler
        formatter = SimpleThreadNameFormatter(normal_log_format)
        handler = logging.StreamHandler(output_file)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)

        # Setup normal logger
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        # Setup stdout and stderr log handler
        formatter = SimpleThreadNameFormatter(output_log_format)
        handler = logging.StreamHandler(output_file)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)

        # Setup stdout logger
        stdout_logger = logging.getLogger("stdout")
        stdout_logger.setLevel(logging.DEBUG)
        stdout_logger.addHandler(handler)

        # Setup stderr logger
        stderr_logger = logging.getLogger("stderr")
        stderr_logger.setLevel(logging.DEBUG)
        stderr_logger.addHandler(handler)

Example:
    To use the loggers from the example above in a subprocess using
    :mod:`.subprocess`, the :class:`.LoggerFile` objects can be created before
    spawning the processes, and closed at the end::

        from iripau.subprocess import run


        # Make sure to close the LoggerFiles
        with (
            LoggerFile(stdout_logger, logging.INFO) as stdout_logger_file,
            LoggerFile(stderr_logger, logging.INFO) as stderr_logger_file
        ):
            output = run(
                ["kubectl", "get", "pods"],
                capture_output=True,
                check=True,
                prompt_tees=[stdout_logger_file],
                stdout_tees=[stdout_logger_file],
                stderr_tees=[stderr_logger_file]
            )

        # Output captured
        print(output.stdout)
        print(output.stderr)
        print(output.returncode)

        # Output logged
        output_file.seek(0)
        print(output_file.read())

Important:
    Closing the :class:`.LoggerFile` objects do not affect the ``output_file``
    created in the first example.

Tip:
    Passing a callable as a tee file in :class:`.subprocess.Popen` causes the
    file to be created (the result of calling it) before spawning the process,
    and closed when it finishes.

Example:
    To log the command, ``stdout`` and ``stderr`` of all of the proceeses spawned
    using :mod:`.subprocess`, a global configuration can be done::

        from functools import partial

        from iripau.subprocess import set_global_prompt_files
        from iripau.subprocess import set_global_stdout_files
        from iripau.subprocess import set_global_stderr_files


        # Create callables that receive no arguments and return a LoggerFile
        stdout_logger_file = partial(LoggerFle, stdout_logger, logging.INFO)
        stderr_logger_file = partial(LoggerFle, stderr_logger, logging.INFO)

        set_global_prompt_files(stdout_logger_file)
        set_global_stdout_files(stdout_logger_file)
        set_global_stderr_files(stderr_logger_file)

        output = run(
            ["kubectl", "get", "pods"],
            capture_output=True,
            check=True
        )

        # Output captured
        print(output.stdout)
        print(output.stderr)
        print(output.returncode)

        # Outpu logged
        output_file.seek(0)
        print(output_file.read())

Tip:
    Disable the use of globally configured loggers by setting to ``False``
    ``add_global_stdout_tees``, ``add_global_stderr_tees`` and/or
    ``add_global_prompt_tees`` in :func:`.subprocess.run` or
    :class:`.subprocess.Popen`::

        output = run(
            ["kubectl", "get", "pods"],
            capture_output=True,
            check=True,
            add_global_stdout_tees=False,
            add_global_stderr_tees=False,
            add_global_prompt_tees=False
        )
"""

import io
import os
import re
import logging
import threading

from typing import Callable, Iterable
from collections import OrderedDict


class LoggerFile:
    """ File-like object that logs every line written to it.
        A thread is created to asynchronously consume the file.
        The thread is joined when the file is closed.

        Args:
            logger: The object used to perform the logging.
            level: The level used to perform the logging.

        Example:
            Get a logger object and use it to create a :class:`.LoggerFile`::

                import logging

                logger = logging.get_logger(__name__)
                logger_file = LoggerFle(logger, logging.DEBUG)

                # Equivalent to logger.debug("A line in a file")
                logger_file.write("A line in a file\\n")

        Example:
            A :class:`.LoggerFile` can be used in a subprocess::

                from subprocess import run

                # The stdout will be logged in real-time
                run(["apt", "install", "-y", "python3"], stdout=logger_file)
    """

    def __new__(cls, logger: logging.Logger, level: int):
        r, w = os.pipe()
        read_file = os.fdopen(r, "r")
        write_file = os.fdopen(w, "w")

        thread = threading.Thread(
            target=cls.log,
            args=(read_file, logger, level),
            name=threading.current_thread().name
        )

        # Close write_file when the thread joins
        cls.patch(thread, "join", write_file.close)

        # Join the thread when the file is closed
        write_file.close = thread.join

        thread.start()
        return write_file

    @staticmethod
    def log(read_file: io.IOBase, logger: logging.Logger, level: int):
        """ Read the whole ``read_file`` line by line and log them using the
            ``logger`` object at the specified logging ``level``.

            This is what will be running in a thread until ``EOF`` is reached.

            Args:
                read_file: A file opened in read mode.
                logger: The object used to perform the logging.
                level: The level used to perform the logging.
        """
        with read_file:
            for line in read_file:
                logger.log(level, line.splitlines()[0])

    @staticmethod
    def patch(instance: object, method_name: str, callback: Callable[[], None]):
        """ Modify ``instance.method_name()`` so that ``callback()`` gets called
            when ``method_name()`` is called. ``callback()`` will be called
            first and then the original ``instance.method_name()``.

            It is used to close the file when the thread is joined.

            Args:
                instance: An object whose method will be patched.
                method_name: The name of the method to patch.
                callback: The function to patch with. It will be called without
                    arguments and its return value will be ignored.

            Example:
                Print a message before closing a file::

                    def print_dummy_message():
                        print("The file is about to be closed...")


                    f = open("/tmp/file.txt")
                    LoggerFle.patch(f, "close", print_dummy_message)

                    # The message will be printed right before the file is closed
                    f.close()
        """
        original_method = getattr(instance, method_name)

        def new_method(*args, **kwargs):
            callback()
            original_method(*args, **kwargs)
        setattr(instance, method_name, new_method)


class SimpleThreadNameFormatter(logging.Formatter):
    """ The same :class:`logging.Formatter` but ``threadName`` is just the first
        token after splitting it: ``record.threadName.split(maxsplit=1)[0]``.

        The constructor arguments are the same as the base class.

        Example:
            Setup a logging handler to use :class:`SimpleThreadNameFormatter`::

                import sys
                import logging

                format = "%(threadName): %(message)s"
                formatter = SimpleThreadNameFormatter(format)
                handler = logging.StreamHandler(sys.stdout)
                handler.setFormatter(formatter)
    """

    def format(self, record):
        """ Override :meth:`logging.Formatter.format` to handle
            ``record.threadName`` as intended.
        """
        if record.threadName:
            record.threadName = record.threadName.split(maxsplit=1)[0]
        return super().format(record)


def group_log_lines(
    lines: Iterable[str],
    thread_id_regex: str,
    main_thread_id: str = "MainThread"
):
    """ For a log file containing entries from several threads, group the lines
        so that the lines coming from the same thread are contiguous, preserving
        the order within the group. Lines coming from the main thread will not
        be grouped.

        Args:
            lines: The lines to group.
            thread_id_regex: The pattern to get the thread name from each line.
                It should have one capturing group, which will be taken as the
                thread name.
            main_thread_id: The name of the main thread.
        Yields:
            str: The next line according to the group ordering.
        Raises:
            ValueError: If a line does not match ``thread_id_regex``.

        Example:
            Open a log file and print the grouped lines::

                import sys

                # The thread name is at the beginning of each line, before ':'
                thread_id_regex = "(.+): .*"

                with open("/tmp/threaded.log") as log_file:
                    sys.stdout.writelines(group_log_lines(log_file))
    """
    lines_map = OrderedDict()
    for i, line in enumerate(lines):
        match = re.match(thread_id_regex, line)
        if not match:
            raise ValueError(f"Invalid log line {i}: '{line}'")

        thread = match.groups()[0]
        if main_thread_id == thread:
            for thread_lines in lines_map.values():
                for thread_line in thread_lines:
                    yield thread_line
            yield line
            lines_map.clear()
        else:
            lines_map[thread] = lines_map.get(thread, []) + [line]

    for thread_lines in lines_map.values():
        for thread_line in thread_lines:
            yield thread_line
