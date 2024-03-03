"""
Tests to validate iripau.logging module
"""

import os
import re
import pytest
import random
import logging
import tempfile
import threading

from time import sleep

from iripau.logging import LoggerFile
from iripau.logging import SimpleThreadNameFormatter
from iripau.logging import group_log_lines


class TestLogging:

    @staticmethod
    def write(stream, text):
        stream.write(text)
        stream.flush()

    @staticmethod
    def read(stream):
        sleep(0.1)
        stream.seek(0)
        return stream.read()

    def test_logger_file(self):
        output_file = tempfile.SpooledTemporaryFile(mode="w+t")

        # Setup log handler
        formatter = SimpleThreadNameFormatter("%(levelname)s: %(message)s")
        handler = logging.StreamHandler(output_file)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)

        # Setup logger
        logger = logging.getLogger("dummy_logger")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        logger_file = LoggerFile(logger, logging.INFO)

        # Write a part of a line
        self.write(logger_file, "Hello,")
        content = self.read(output_file)
        assert "" == content

        # Write the rest of the line
        self.write(logger_file, " bye\n")
        content = self.read(output_file)
        assert content.endswith(
            "INFO: Hello, bye\n"
        )

        # Write several lines
        self.write(
            logger_file,
            "SomeString\n"
            "AnotherString\n"
            "TestString\n"
            "DummyString\n"
        )

        content = self.read(output_file)
        assert content.endswith(
            "INFO: SomeString\n"
            "INFO: AnotherString\n"
            "INFO: TestString\n"
            "INFO: DummyString\n"
        )

        # Write a long line
        self.write(
            logger_file,
            "SomeString AnotherString TestString DummyString\n"
        )

        content = self.read(output_file)
        assert content.endswith(
            "INFO: SomeString AnotherString TestString DummyString\n"
        )

        # Write one line using file descriptor
        fd = logger_file.fileno()
        os.write(fd, b"Another dummy string\n")
        content = self.read(output_file)
        assert content.endswith(
            "INFO: Another dummy string\n"
        )

        # Write several lines using file descriptor
        self.write(
            logger_file,
            "Line1\n"
            "Line2\n"
            "Line3\n"
            "Line4\n"
        )

        logger_file.close()
        content = self.read(output_file)
        assert content.endswith(
            "INFO: Line1\n"
            "INFO: Line2\n"
            "INFO: Line3\n"
            "INFO: Line4\n"
        )

    @staticmethod
    def log_stuff(id, normal_logger, stdout_logger, stderr_logger):
        sleep(random.uniform(0.1, 0.3))
        normal_logger.info(f"{id} - First line")

        sleep(random.uniform(0.1, 0.3))
        stdout_logger.info(f"{id} - Simulated output")

        sleep(random.uniform(0.1, 0.3))
        stderr_logger.info(f"{id} - Simulated error")

        sleep(random.uniform(0.1, 0.3))
        normal_logger.info(f"{id} - Last line")

    @classmethod
    def log_stuff_in_threads(cls, ids, *loggers):
        threads = [
            threading.Thread(target=cls.log_stuff, args=(id, *loggers))
            for id in ids
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

    def test_group_log_lines(self):
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

        self.log_stuff_in_threads((1, 2), logger, stdout_logger, stderr_logger)
        logger.info("Line from Main")
        self.log_stuff_in_threads((3, 4), logger, stdout_logger, stderr_logger)

        pattern = (
            ".{34}: (1|2) - First line\n"
            ".{34}: \\[stdout\\] \\1 - Simulated output\n"
            ".{34}: \\[stderr\\] \\1 - Simulated error\n"
            ".{34}: \\1 - Last line\n"
            ".{34}: (1|2) - First line\n"
            ".{34}: \\[stdout\\] \\2 - Simulated output\n"
            ".{34}: \\[stderr\\] \\2 - Simulated error\n"
            ".{34}: \\2 - Last line\n"
            ".{34}: Line from Main\n"
            ".{34}: (3|4) - First line\n"
            ".{34}: \\[stdout\\] \\3 - Simulated output\n"
            ".{34}: \\[stderr\\] \\3 - Simulated error\n"
            ".{34}: \\3 - Last line\n"
            ".{34}: (3|4) - First line\n"
            ".{34}: \\[stdout\\] \\4 - Simulated output\n"
            ".{34}: \\[stderr\\] \\4 - Simulated error\n"
            ".{34}: \\4 - Last line\n"
        )

        content = self.read(output_file)
        assert not re.fullmatch(pattern, content)  # Verify content is scrambled

        output_file.seek(0)
        grouped_lines = group_log_lines(output_file, r".* - \s*([^:\s]+).*: .*")
        assert re.fullmatch(pattern, "".join(grouped_lines))

    def test_group_log_lines_invalid(self):
        lines = ["Some log line\n"]
        with pytest.raises(ValueError):
            list(group_log_lines(lines, "unmatching regex"))
