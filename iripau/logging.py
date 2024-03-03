"""
Logging utilities
"""

import os
import re
import logging
import threading

from collections import OrderedDict


class LoggerFile:
    """ File that logs every line written to it """

    def __new__(cls, logger, level):
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
    def log(read_file, logger, level):
        with read_file:
            for line in read_file:
                logger.log(level, line.splitlines()[0])

    @staticmethod
    def patch(instance, function_name, callback):
        original_function = getattr(instance, function_name)

        def new_function():
            callback()
            original_function()
        setattr(instance, function_name, new_function)


class SimpleThreadNameFormatter(logging.Formatter):
    """ The same logging.Formatter but threadName is just the first token after
        splitting it: record.threadName.split(maxsplit=1)[0]
    """

    def format(self, record):
        if record.threadName:
            record.threadName = record.threadName.split(maxsplit=1)[0]
        return super().format(record)


def group_log_lines(lines, thread_id_regex, main_thread_id="MainThread"):
    """ For a log file containing entries from several threads, group the lines
        so that the lines coming from the same thread are contiguous, preserving
        order within the group. Logs coming from MainThread will not be grouped.
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
