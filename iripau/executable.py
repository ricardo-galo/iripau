"""
Execute Command-Line Interfaces (CLI) as Python functions.

Call an instance of :class:`.Executable`, or any of its attributes, passing
positional arguments as ``*args`` and optional arguments as ``**kwargs``.
All of the quoting is handled automatically, so there is no need to handle spaces
nor any special characters such as single and double quotes.
The attributes of the object will be instances of :class:`Command`.
The return value is an instance of :class:`subprocess.CompletedProcess`.

Example:
    Make a ``docker`` wrapper::

        docker = Executable("docker")

        # docker --version
        output = docker(version=True)

        # docker run ubuntu:24.04 --volume=/tmp/data:/data:Z --name=test-container
        output = docker.run("ubuntu:24.04", volume="/tmp/data:/data:Z", name="test-container")

        # docker container rename test-container renamed-container
        output = docker.container.rename("test-container", "renamed-container")

Note:
    All values for positional and optional arguments are converted to string
    with ``str(value)`` before creating the final subproces command.
"""

from shlex import split
from random import choice
from typing import Any, Callable, Iterable, Tuple
from itertools import chain

from iripau.command import host_run


class Command:
    """ Run a command or sub-command of a CLI as a Python function.

        The attributes of :class:`.Executable` will be instances of this class,
        as well as any other sub-attribute.

        Args:
            parent (:class:`.Executable` | :class:`.Command`): Object to
                call so the subprocess can actually be executed.
            command: Python identifier for a given command or cub-command.
    """

    def __init__(self, parent, command: str):
        self._parent = parent
        self._command = parent._mk_command(command)
        self._mk_command = parent._mk_command

    def __getattr__(self, command):
        child = Command(self, command)
        setattr(self, command, child)
        return child

    def __call__(self, *args, **kwargs):
        return self._parent(self._command, *args, **kwargs)


def make_command(command: str) -> str:
    """ Replace underscore with dash.

        Suitable for a CLI that uses dashes as word-separator in their
        positional arguments.

        Args:
            command: Python identifier referring to a CLI command or sub-command.

        Returns:
            Final token to be used as a CLI positional argument.
    """
    return command.replace("_", "-")


def make_option(option: str) -> Tuple[str]:
    """ Replace underscore with dash and prepend two more dashes.

        Suitable for a CLI that uses dashes as word-separator in their
        positional arguments.

        Args:
            option: Python identifier referring to a CLI optional argument.

        Returns:
            The tokens that could be used as a CLI positional argument.
    """
    return "--" + option.replace("_", "-"),


class Executable:
    """ Run an executable as a Python callable.

        Args:
            executable: Path to an executable file or just the name if it exists
                in the ``PATH``. Or tokens that refer to a command.
            make_command: Function to convert a Python identifier to the
                corresponding command positional argument for the CLI.
            make_option: Function to convert a Python identifier into the
                corresponding optional argument for the CLI.
            alias: Alias for ``executable``. See ``alias`` in
                :class:`iripau.subprocess.Popen`.
            run_args_prefix: When calling an instance of this class, all of the
                ``**kwargs`` starting with this prefix will be passed to
                ``run_function`` after removing the prefix.
            run_function: The function that will actually run the process, wait
                for it and return a :class:`subprocess.CompletedProcess`,
                preferably.
                If ``None``, the default will be :func:`iripau.command.host_run`.
            **kwargs: Keyword arguments to be passed to ``run_function`` every
                time this object is called.
                The ``run_args_prefix`` is not needed here.


        **Regarding optional arguments:**

        Most of the CLIs have a long and short version for the same option,
        for example ``docker run -m 128m`` and ``docker run --memory=128m``.
        By default only one of those option can be used::

            # docker run ubuntu:24.04 -m 128m
            docker.run("ubuntu:24.04", m="128m")

            # docker run ubuntu:24.04 --memory=128m
            docker.run("ubuntu:24.04", memory="128m")

        But using the name of a short option in a Python function might reduce
        readability.
        To solve that issue, the ``get`` method of a dictionary can be used as
        ``make_option``.
        The keys of the dictionaries would be the Python identifiers used when
        calling the object::

            options_map = {
                "config": ("-c",),
                "memory": ("-m"),
                "quiet": ("-q",)
            }

            docker = Executable("docker", make_option=options_map.get)

            # docker run ubuntu:24.04 -m 128m
            output = docker.run("ubuntu:24.04", memory="128m")

        Also, the dictionary can be used in combination with the default function,
        :func:`.make_option`, or any other function to avoid having all of the
        options supported by the CLI in the dictionary::

            option_map = {...}

            def make_option(option):
                tokens = options_map.get(option)
                if tokens is None:
                    tokens = make_option(option)
                return tokens

            docker = Executable("docker", make_option=make_option)

        Tip:
            Using a dictionary can help on ``make_command`` as well.

        As you might have already noted, the values of the dictionary are tuples.
        If that tuple has more that one item, one of those will be chosen randomly.
        If the chosen option starts with ``--``, there will be a single token
        with the option and the value: ``--memory=128m``.
        If not, there will be two tokens: ``-m 128m``.

        **Regarding the values that the optional arguments can have:**

        | If ``True``, the option will be treated as a flag, with no value:
        | **From:** ``help=True``
        | **To:** ``--help``

        | If ``False`` or ``None``, the option will be ignored:
        | **From:** ``help=False`` or ``help=None``
        | **To:** Nothing, not even an empty string

        | If an iterable and not a string, the option will be repeated for each item:
        | **From:** ``env=["DB_PASS=0123", "DB_PORT=3210"]``
        | **To:** ``-e DB_PASS=0123 -e DB_PORT=3210``
    """

    def __init__(
        self,
        executable: Iterable[str] | str,
        make_command: Callable[[str], str] = make_command,
        make_option: Callable[[str], Tuple[str]] = make_option,
        alias: Iterable[str] | str = None,
        run_args_prefix: str = "_",
        run_function: Callable[[Iterable[str], Any], Any] = None,
        **kwargs
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
    def _make_arg(cls, options, value):
        """ Return a list of tokens. Randomly choose a short or long option.
            If a ``value`` is given it's appended appropriately.
            If ``value`` is iterable, the option will be repeated for each item.
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
