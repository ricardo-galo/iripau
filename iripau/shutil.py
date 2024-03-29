"""
Shell utilities
"""

import os
import errno
import select
import shutil
import contextlib

from iripau.functools import wait_for


class FileLock:
    poll_time = 0.05

    def __init__(self, file_name, timeout=None):
        self.file_name = file_name
        self.timeout = timeout
        self.acquired = False

    def __enter__(self):
        self.acquire(self.timeout)
        return self

    def __exit__(self, type, value, traceback):
        self.release()

    def __del__(self):
        self.release()

    def _lock_file_created(self):
        """ Lock file could be created by us """
        try:
            self.fd = os.open(
                self.file_name,
                os.O_CREAT | os.O_EXCL | os.O_RDWR
            )
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        else:
            return True
        return False

    def acquire(self, timeout=None):
        if not self.acquired:
            wait_for(
                self._lock_file_created,
                _timeout=timeout or self.timeout,
                _poll_time=self.poll_time
            )
            self.acquired = True

    def release(self):
        if self.acquired:
            os.close(self.fd)
            os.unlink(self.file_name)
            self.acquired = False


def create_file(file_name, content=""):
    mode = "wb" if bytes == type(content) else "w"
    with open(file_name, mode) as f:
        f.write(content)


def read_file(file_name, binary=False):
    mode = "rb" if binary else "r"
    with open(file_name, mode) as f:
        return f.read()


def remove_file(file_name):
    with contextlib.suppress(FileNotFoundError):
        os.remove(file_name)


def remove_tree(root):
    with contextlib.suppress(FileNotFoundError):
        if os.path.isdir(root) and not os.path.islink(root):
            shutil.rmtree(root)
        else:
            os.remove(root)


@contextlib.contextmanager
def file_created(file_name, content=""):
    create_file(file_name, content)
    try:
        yield file_name
    finally:
        os.remove(file_name)


def wait_for_file(file_obj, *args, **kwargs):
    poll_obj = select.poll()
    poll_obj.register(file_obj, select.POLLIN)
    wait_for(lambda: poll_obj.poll(0), *args, **kwargs)


def _rotate(root, ext, seq=0):
    old = seq and f"{root}.{seq}{ext}" or root + ext
    if os.path.exists(old):
        seq += 1
        _rotate(root, ext, seq)
        os.rename(old, f"{root}.{seq}{ext}")


def rotate(path, seq=0):
    _rotate(*os.path.splitext(path))
