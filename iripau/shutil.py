"""
Generic and stand-alone shell utilities.
"""

import io
import os
import errno
import select
import shutil
import contextlib

from iripau.functools import wait_for


class FileLock:
    """ Provides a file‐based lock to ensure that only one thread or process
        can access a shared resource at a time.

        The lock is implemented by creating a lock file at the specified path.
        Acquisition blocks until the lock file can be exclusively created without
        contention. Supports optional timeout and context‐manager protocol.

        Args:
            file_name: Filesystem path to the lock file.
            timeout: Maximum time in seconds to wait for the lock.

        Attributes:
            lock_path (str): Filesystem path to the lock file.
            timeout (Optional[float]): Maximum time in seconds to wait for the lock.
            acquired (boot): Whether the file lock is acquired by this object.
    """

    #: float: Time to wait between file creation tries.
    poll_time = 0.05

    def __init__(self, file_name: str, timeout: float = None):
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

    def acquire(self, timeout: float = None):
        """
            Block until the file lock is exclusively created.

            Args:
                timeout: Override the maximum time in seconds to wait for the lock.

            Raises:
                TimeoutError: If timeout reached.
        """
        if not self.acquired:
            wait_for(
                self._lock_file_created,
                _timeout=timeout or self.timeout,
                _poll_time=self.poll_time
            )
            self.acquired = True

    def release(self):
        """ Release a lock. If locked, remove the file previously created. """
        if self.acquired:
            os.close(self.fd)
            os.unlink(self.file_name)
            self.acquired = False

    def locked(self):
        """ Whether the file lock is acquired. """
        return self.acquired


def create_file(file_name: str, content: bytes | str = ""):
    """ Create a file with the specified ``content``.

        Args:
            file_name: Path to the file to be created or overrode.
            content: The file will be created with this data.
    """
    mode = "wb" if bytes == type(content) else "w"
    with open(file_name, mode) as f:
        f.write(content)


def read_file(file_name: str, binary: bool = False) -> bytes | str:
    """ Return the content of a file.

        Args:
            file_name: Path to the file to read.
            binary: Whether the file content is binary.

        Returns:
            The content of the file.
    """
    mode = "rb" if binary else "r"
    with open(file_name, mode) as f:
        return f.read()


def remove_file(file_name: str):
    """ Delete a file.
        If the file does not exist, do nothing.

        Args:
            file_name: Path to the file to delete.
    """
    with contextlib.suppress(FileNotFoundError):
        os.remove(file_name)


def remove_tree(root: str):
    """ Delete a file or a directory.
        If ``root`` does not exist, do nothing.

        Args:
            root: Path to the file or directory to delete.
    """
    with contextlib.suppress(FileNotFoundError):
        if os.path.isdir(root) and not os.path.islink(root):
            shutil.rmtree(root)
        else:
            os.remove(root)


@contextlib.contextmanager
def file_created(file_name: str, content: bytes | str = ""):
    """ A context-manager that creates a file with the desired content at enter
        and delete it at exit.

        Args:
            file_name: Path to the file to be created or overrode.
            content: The file will be created with this data.

        Yields:
            str: The ``file_name``.

        Example:
            Create a file, send it to a remote host and delete it::

                import subprocess


                with file_created("/tmp/example.txt", "Some content") as file_name:
                    # scp /tmp/example.txt host:/tmp/
                    subprocess.run(["scp", file_name, "host:/tmp/"])
    """
    create_file(file_name, content)
    try:
        yield file_name
    finally:
        os.remove(file_name)


def wait_for_file(file_obj: io.IOBase, *args, **kwargs):
    """ Block until there is new data to be read in ``file_obj``.

        Args:
            file_obj: A file opened to read.
            *args: Passed to :func:`.functools.wait_for`.
            **kwargs: Passed to :func:`.functools.wait_for`.
    """
    poll_obj = select.poll()
    poll_obj.register(file_obj, select.POLLIN)
    wait_for(lambda: poll_obj.poll(0), *args, **kwargs)


def _rotate(root, ext, seq=0):
    old = seq and f"{root}.{seq}{ext}" or root + ext
    if os.path.exists(old):
        seq += 1
        _rotate(root, ext, seq)
        os.rename(old, f"{root}.{seq}{ext}")


def rotate(path: str, seq: int = 0):
    """ Rotate file or directory backups by renaming existing entries with
        incrementing suffixes. File extensions are preserved.

        Args:
            path: Path to the file or directory to rotate.
            seq: Initial sequence index, normally left at 0.

        Example:
            Rotate a log file and its backups so that a new ``log.txt`` can be
            created without overiding the previous log files::

                # To cause the following effect:
                # | Original files | Renamed files |
                # | -------------- | ------------- |
                # | log.txt        | log.1.txt     |
                # | log.1.txt      | log.2.txt     |
                # | log.2.txt      | log.3.txt     |

                rotate("log.txt")
    """
    _rotate(*os.path.splitext(path))
