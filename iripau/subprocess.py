"""
A wrapper of the subprocess module

This module relies on the following system utilities being installed:
* bash
* kill
* pstree
* tee
"""

import io
import os
import re
import sys
import shlex
import psutil
import subprocess

from subprocess import DEVNULL
from subprocess import PIPE
from subprocess import STDOUT
from subprocess import CompletedProcess
from subprocess import TimeoutExpired
from subprocess import SubprocessError  # noqa: F401
from subprocess import CalledProcessError

from time import time
from typing import Union, Iterable, Callable
from tempfile import SpooledTemporaryFile
from contextlib import contextmanager, nullcontext

FILE = -4
GLOBAL_ECHO = False
GLOBAL_STDOUTS = set()
GLOBAL_STDERRS = set()
GLOBAL_PROMPTS = set()


TeeStream = Union[io.IOBase, Callable[[], io.IOBase]]
TeeStreams = Iterable[TeeStream]


class PipeFile(SpooledTemporaryFile):
    """ A file to be used as stdin, stdout and stderr in Popen to avoid dead lock
        when the process output is too long using PIPE.

        If used as stdin, the content should be written before spawning the process.
    """

    def __init__(self, content=None, encoding=None, errors=None, text=None):
        super().__init__(
            mode="w+t" if text else "w+b",
            encoding=encoding,
            errors=errors
        )

        if content:
            self.write(content)
            self.seek(0)

    def read_all(self):
        self.seek(0)
        return self.read()


class Tee(subprocess.Popen):
    """ A subprocess to send real-time input to several file descriptors """

    def __init__(self, input, fds, output=None, encoding=None, errors=None, text=None):
        if output is STDOUT:
            raise ValueError("output cannot be STDOUT")

        if output is None:
            output = DEVNULL

        fds = normalize_outerr_fds(fds)
        if 1 in fds:
            if output != DEVNULL:
                fds.add(2)
            stdout = None
            stderr = output
        elif 2 in fds:
            stdout = output
            stderr = None
        else:
            stdout = output
            stderr = DEVNULL

        fds.discard(1)
        super().__init__(
            stdin=input, stdout=stdout, stderr=stderr, pass_fds=fds - {2},
            encoding=encoding, errors=errors, text=text, **self.get_kwargs(fds)
        )

        self.output = self.stdout if self.stderr is None else self.stderr

    @staticmethod
    def get_cmd(fds):
        return ["tee", "-a"] + [f"/dev/fd/{fd}" for fd in fds]

    if os.access("/dev/fd/2", os.W_OK):
        @classmethod
        def get_kwargs(cls, fds):
            return {"args": cls.get_cmd(fds)}
    else:
        @classmethod
        def get_kwargs(cls, fds):
            if 2 in fds:
                return {
                    "args": " ".join(cls.get_cmd(fds - {2})) + " >(cat >&2)",
                    "shell": True
                }
            return {"args": cls.get_cmd(fds)}

    def communicate(self, *args, **kwargs):
        stdout, stderr = super().communicate(*args, **kwargs)
        return stdout if stderr is None else stderr


class Popen(subprocess.Popen):
    """ A subprocess.Popen that can send its stdout and stderr to several files
        in real-time keeping the ability of capturing its output.
    """

    def __init__(
        self, args, *, cwd=None, env=None, encoding=None, errors=None, text=None,
        stdout_tees: TeeStreams = [], add_global_stdout_tees=True,
        stderr_tees: TeeStreams = [], add_global_stderr_tees=True,
        prompt_tees: TeeStreams = [], add_global_prompt_tees=True,
        echo=None, alias=None, comment=None, **kwargs
    ):
        stdout = kwargs.get("stdout")
        stderr = kwargs.get("stderr")

        stdout_tees, stderr_tees, prompt_tees, new_tees, err2out = self._get_tee_sets(
            stdout_tees, add_global_stdout_tees,
            stderr_tees, add_global_stderr_tees,
            prompt_tees, add_global_prompt_tees,
            echo, stdout, stderr
        )

        self.new_tees = new_tees

        stdout_fds = {tee.fileno() for tee in stdout_tees}
        stderr_fds = {tee.fileno() for tee in stderr_tees}
        prompt_fds = {tee.fileno() for tee in prompt_tees}

        if stdout_fds:
            kwargs["stdout"] = PIPE

        if stderr_fds:
            kwargs["stderr"] = PIPE

        if prompt_fds:
            stream_prompts(prompt_fds, alias or args, cwd, env, err2out, comment)

        super().__init__(args, cwd=cwd, env=env,
                         encoding=encoding, errors=errors, text=text, **kwargs)

        self.original_stdout = self.stdout
        self.original_stderr = self.stderr

        stdout_process = stderr_process = self
        if stdout_fds:
            stdout_process = Tee(self.stdout, stdout_fds, stdout, encoding, errors, text)
            self.stdout = stdout_process.output
        if stderr_fds:
            stderr_process = Tee(self.stderr, stderr_fds, stderr, encoding, errors, text)
            self.stderr = stderr_process.output

        self.stdout_process = stdout_process
        self.stderr_process = stderr_process

    def __del__(self):
        self._close_tee_files(self.new_tees)
        super().__del__()

    @staticmethod
    def _get_tee_files(tees: TeeStreams, new_tee_files):
        """ If any tee in tees is a function, store the return value in new_tee_files"""
        tee_files = set()
        for tee in tees:
            if callable(tee):
                tee = tee()
                new_tee_files.append(tee)
            tee_files.add(tee)
        return tee_files

    @staticmethod
    def _close_tee_files(tees):
        while tees:
            try:
                tees.pop().close()
            except Exception:
                pass

    @classmethod
    def _get_tee_sets(
        cls,
        stdout_tees, add_global_stdout_tees,
        stderr_tees, add_global_stderr_tees,
        prompt_tees, add_global_prompt_tees,
        echo, stdout, stderr
    ):
        stdout_tees = set(stdout_tees)
        stderr_tees = set(stderr_tees)
        prompt_tees = set(prompt_tees)

        if add_global_prompt_tees:
            prompt_tees.update(GLOBAL_PROMPTS)
        if add_global_stdout_tees:
            stdout_tees.update(GLOBAL_STDOUTS)
        if add_global_stderr_tees:
            stderr_tees.update(GLOBAL_STDERRS)

        if echo is None:
            echo = GLOBAL_ECHO

        if echo:
            prompt_tees.add(sys.stdout)
            stdout_tees.add(sys.stdout)
            stderr_tees.add(sys.stderr)

        if stdout is None:
            if stdout_tees == {sys.stdout}:
                stdout_tees.clear()  # tee process not needed for stdout
            if stdout_tees:
                stdout_tees.add(sys.stdout)

        if stderr is None:
            if stderr_tees == {sys.stderr}:
                stderr_tees.clear()  # tee process not needed for stderr
            if stderr_tees:
                stderr_tees.add(sys.stderr)

        if stderr is STDOUT:
            err2out = True
            stderr_tees = set()
        else:
            err2out = False

        new_tees = []
        return (
            cls._get_tee_files(stdout_tees, new_tees),
            cls._get_tee_files(stderr_tees, new_tees),
            cls._get_tee_files(prompt_tees, new_tees),
            new_tees, err2out
        )

    @classmethod
    def simulate(
        cls, cmd, stdout, stderr, encoding=None, errors=None, text=None, comment=None,
        stdout_tees: TeeStreams = [], add_global_stdout_tees=True,
        stderr_tees: TeeStreams = [], add_global_stderr_tees=True,
        prompt_tees: TeeStreams = [], add_global_prompt_tees=True,
        echo=None
    ):
        stdout_tees, stderr_tees, prompt_tees, new_tees, err2out = cls._get_tee_sets(
            stdout_tees, add_global_stdout_tees,
            stderr_tees, add_global_stderr_tees,
            prompt_tees, add_global_prompt_tees,
            echo, DEVNULL, DEVNULL
        )

        if not (stdout_tees or stderr_tees or prompt_tees):
            return

        try:
            stdout_fds = {tee.fileno() for tee in stdout_tees}
            stderr_fds = {tee.fileno() for tee in stderr_tees}
            prompt_fds = {tee.fileno() for tee in prompt_tees}

            if prompt_fds:
                stream_prompts(prompt_fds, cmd, None, None, err2out, comment)

            if stdout_fds:
                with Tee(PIPE, stdout_fds, DEVNULL, encoding, errors, text) as tee:
                    tee.communicate(stdout)

            if stderr_fds:
                with Tee(PIPE, stderr_fds, DEVNULL, encoding, errors, text) as tee:
                    tee.communicate(stderr)
        finally:
            cls._close_tee_files(new_tees)

    def get_pids(self):
        """ Return the pid for all of the processes in the tree """
        output = run(
            ["pstree", "-p", str(self.pid)],
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=DEVNULL,
            text=True,
            check=True
        )

        return re.findall("\\((\\d+)\\)", output.stdout)[::-1]

    def terminate_tree(self):
        run(
            ["kill"] + self.get_pids(),
            stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL,
        )

    def kill_tree(self):
        run(
            ["kill", "-9"] + self.get_pids(),
            stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL,
        )

    def end_tree(self, sigterm_timeout):
        """ Try to gracefully terminate the process tree,
            kill it after 'sigterm_timeout' seconds
        """
        if sigterm_timeout:
            self.terminate_tree()
            try:
                self.communicate(timeout=sigterm_timeout)
            except:  # noqa: E722
                self.kill_tree()
        else:
            self.kill_tree()

    def poll(self):
        processes = {self.stderr_process, self.stdout_process} - {self}
        if all(process.poll() is not None for process in processes):
            return super().poll()

    def wait(self, timeout=None):
        processes = {self.stderr_process, self.stdout_process} - {self}
        for process in processes:
            process.wait(timeout)
            timeout = None
        return super().wait(timeout)

    @contextmanager
    def _streams_restored(self):
        self.stdout = self.original_stdout
        self.stderr = self.original_stderr
        try:
            yield
        finally:
            self.stdout = self.stdout_process.stdout
            self.stderr = self.stderr_process.stderr

    @contextmanager
    def _stdin_none(self):
        original_stdin = self.stdin
        self.stdin = None
        try:
            yield
        finally:
            self.stdin = original_stdin

    def _communicate_tees(self, timeout):
        stdout = stderr = None
        if self.stdout_process is not self:
            stdout = self.stdout_process.communicate(timeout=timeout)
            timeout = None
        if self.stderr_process is not self:
            stderr = self.stderr_process.communicate(timeout=timeout)
            timeout = None
        self._close_tee_files(self.new_tees)
        return stdout, stderr, timeout

    def _communicate_all(self, timeout):
        stdout, stderr, timeout = self._communicate_tees(timeout)
        main_stdout, main_stderr = super().communicate(timeout=timeout)
        return (
            main_stdout if self.stdout_process is self else stdout,
            main_stderr if self.stderr_process is self else stderr
        )

    @property
    def _any_communication_started(self):
        return (
            self.stdout_process._communication_started or
            self.stderr_process._communication_started or
            self._communication_started
        )

    def communicate(self, input=None, timeout=None):
        if self._any_communication_started and input:
            raise ValueError("Cannot send input after starting communication")

        with self._streams_restored():
            if self.stdin and input:
                self._stdin_write(input)
                with self._stdin_none():
                    return self._communicate_all(timeout)
            return self._communicate_all(timeout)


def normalize_outerr_fds(fds: Iterable[int]):
    """ Return fds as a set but using 1 and 2 for stdout and stderr file
        descriptors in case we are being redirected
    """
    out_fd = sys.stdout.fileno()  # This might not always be 1
    err_fd = sys.stderr.fileno()  # This might not always be 2
    fds = set(fds)
    if out_fd in fds:
        fds.remove(out_fd)
        fds.add(1)
    if err_fd in fds:
        fds.remove(err_fd)
        fds.add(2)
    return fds


def quote(cmd: Iterable[str]):
    """ Convert the command tokens into a single string that could be pasted into
        the shell to execute the original command
    """
    return " ".join(map(shlex.quote, cmd))


def shellify(cmd: Union[str, Iterable[str]], err2out=False, comment=None):
    """ Quote command if needed and optionally add extra strings to express
        stderr being redirected to stdout and a comment
    """
    if not isinstance(cmd, str):
        cmd = quote(cmd)
    if err2out:
        cmd += " 2>&1"
    if comment:
        cmd += f" # {comment}"
    return cmd


# If bash is installed and supports prompt expansion
if subprocess.run(
    ["bash", "-c", "echo ${0@P}"],
    stdin=DEVNULL,
    stdout=DEVNULL,
    stderr=DEVNULL
).returncode == 0:
    HOME = os.path.expanduser("~")
    PS1, PS2 = subprocess.run(
        ["bash", "-ic", "echo \"$PS1\"; echo \"$PS2\""],
        text=True,
        stdin=DEVNULL,
        stdout=PIPE,
        stderr=DEVNULL
    ).stdout.splitlines()[-2:]

    def stream_prompts(fds: Iterable[int], cmd, cwd=None, env=None, err2out=False, comment=None):
        """ Write shell prompt and command into file descriptors fds """
        fds = normalize_outerr_fds(fds)
        custom_env = {"CPS1": PS1, "CPS2": PS2}
        custom_env.update(env or {})
        custom_env.setdefault("HOME", HOME)
        script = (
            "(\n"
            "    IFS= read -r \"line\"\n"
            "    echo \"${CPS1@P}${line}\"\n"
            "    while IFS= read -r \"line\"; do\n"
            "        echo \"${CPS2@P}${line}\"\n"
            "    done\n"
            ") | " + quote(Tee.get_cmd(fds - {1}))
        )
        subprocess.run(
            ["bash", "-c", script],
            text=True,
            input=shellify(cmd, err2out, comment) + "\n",
            stdout=None if 1 in fds else DEVNULL,
            stderr=None if 2 in fds else DEVNULL,
            pass_fds=fds - {1, 2},
            cwd=cwd,
            env=custom_env,
            check=True
        )
else:  # Use hard-coded PS1 and PS2 strings
    def stream_prompts(fds: Iterable[int], cmd, cwd=None, env=None, err2out=False, comment=None):
        """ Write shell prompt and command into file descriptors fds """
        cmd = shellify(cmd, err2out, comment) + "\n"
        input = "$ " + "> ".join(cmd.splitlines(keepends=True))
        with Tee(PIPE, fds, DEVNULL, text=True) as tee:
            tee.communicate(input=input)


def set_global_echo(value):
    global GLOBAL_ECHO
    GLOBAL_ECHO = bool(value)


def set_global_stdout_files(*files: TeeStream):
    global GLOBAL_STDOUTS
    GLOBAL_STDOUTS = set(files)


def set_global_stderr_files(*files: TeeStream):
    global GLOBAL_STDERRS
    GLOBAL_STDERRS = set(files)


def set_global_prompt_files(*files: TeeStream):
    global GLOBAL_PROMPTS
    GLOBAL_PROMPTS = set(files)


def _output_context(kwargs, key, encoding, errors, text):
    """ Create a PipeFile, store it in kwargs[key] and return it if it is FILE.
        Just return a nullcontext otherwise.
    """
    if kwargs.get(key) is FILE:
        kwargs[key] = PipeFile(encoding=encoding, errors=errors, text=text)
        return kwargs[key]
    return nullcontext()


def run(
    args, *, input=None, capture_output=False, timeout=None, check=False,
    encoding=None, errors=None, text=None, sigterm_timeout=10, comment=None, **kwargs
):
    """ A subprocess.run that instantiates this module's Popen """
    if input is not None:
        if kwargs.get("stdin") is not None:
            raise ValueError("stdin and input arguments may not both be used.")
        kwargs["stdin"] = PIPE

    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used with capture_output.")
        kwargs["stdout"] = FILE
        kwargs["stderr"] = FILE

    comment = " ".join((comment or "", f"timeout={timeout}" if timeout else "")).strip()
    with (
        _output_context(kwargs, "stdout", encoding, errors, text) as stdout_file,
        _output_context(kwargs, "stderr", encoding, errors, text) as stderr_file,
        Popen(args, encoding=encoding, errors=errors, text=text,
              comment=comment, **kwargs) as process
    ):
        start = psutil.Process(process.pid).create_time()
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except TimeoutExpired:
            process.end_tree(sigterm_timeout)
            process.wait()
            raise
        except:  # noqa: E722
            process.kill_tree()
            raise
        finally:
            end = time()
            returncode = process.poll()

        if stdout_file:
            stdout = stdout_file.read_all()
        if stderr_file:
            stderr = stderr_file.read_all()

        if check and returncode:
            raise CalledProcessError(returncode, process.args, output=stdout, stderr=stderr)

        output = CompletedProcess(process.args, returncode, stdout, stderr)
        output.time = end - start
        return output


def call(*args, **kwargs):
    return run(*args, **kwargs).returncode


def check_call(*args, **kwargs):
    kwargs["check"] = True
    return call(*args, **kwargs)


def check_output(*args, **kwargs):
    kwargs["check"] = True
    kwargs.setdefault("stdout", PIPE)
    return run(*args, **kwargs).stdout


def getoutput(*args, **kwargs):
    return getstatusoutput(*args, **kwargs)[1]


def getstatusoutput(*args, **kwargs):
    kwargs["stdout"] = PIPE
    kwargs["stderr"] = STDOUT
    kwargs["shell"] = True
    kwargs["text"] = True
    output = run(*args, **kwargs)
    return (output.returncode, output.stdout)
