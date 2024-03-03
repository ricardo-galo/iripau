"""
Execute commands as Python functions
"""

from shlex import split
from random import choice
from itertools import chain

from iripau.command import host_run


class Command:
    """ Run an executable command as a Python callable """

    def __init__(self, parent, command):
        self._parent = parent
        self._command = parent._mk_command(command)
        self._mk_command = parent._mk_command

    def __getattr__(self, command):
        child = Command(self, command)
        setattr(self, command, child)
        return child

    def __call__(self, *args, **kwargs):
        return self._parent(self._command, *args, **kwargs)


def make_command(command):
    return command.replace("_", "-")


def make_option(option):
    return "--" + option.replace("_", "-"),


class Executable:
    """ Run an executable as a Python callable """

    def __init__(
        self, executable, make_command=make_command, make_option=make_option,
        alias=None, run_args_prefix="_", run_function=None, **kwargs
    ):
        self._run = run_function or host_run
        self._exe = split(executable) if isinstance(executable, str) else executable
        self._alias = split(alias) if isinstance(alias, str) else alias
        self._kwargs = kwargs

        self._prefix = run_args_prefix
        self._mk_option = make_option
        self._mk_command = make_command

    def __getattr__(self, command):
        child = Command(self, command)
        setattr(self, command, child)
        return child

    def __call__(self, *args, **kwargs):
        optionals = chain.from_iterable(
            self._make_arg(self._mk_option(key), value)
            for key, value in kwargs.items()
            if not key.startswith(self._prefix)
        )

        positionals = list(map(str, args))
        optionals = list(optionals)

        kwargs = {
            key[len(self._prefix):]: value
            for key, value in kwargs.items()
            if key.startswith(self._prefix)
        }

        if self._alias:
            kwargs.setdefault("alias", self._alias + positionals + optionals)

        cmd = self._exe + positionals + optionals
        return self._run(cmd, **self._kwargs, **kwargs)

    @staticmethod
    def _is_iterable(value):
        if isinstance(value, (str, bytes)):
            return False
        return hasattr(value, "__iter__")

    @classmethod
    def _make_arg(cls, options, value=None):
        """ Return a list of tokens. Randomly choose a short or long option.
            If a 'value' is given it's appended appropriately.
            If 'value' is iterable, the option will be repeated for each item.
        """
        if cls._is_iterable(value):
            return chain.from_iterable(
                cls._make_arg(options, item)
                for item in value
            )

        if value in {None, False}:
            return []

        option = choice(options)
        if value is True:
            return [option]

        value = str(value)
        if option.startswith("--"):
            return [option + "=" + value]
        return [option, value]
