"""
A wrapper of the :mod:`requests` module that has extra features.

In theory, the original :mod:`requests` module can be replaced with :mod:`.requests`
keeping the original functionality. After that, the extra features can be leveraged.

Currently, the only extra feature is simulating a ``curl`` command. If a global
configuration is made as in the examples mentioned in :mod:`.logging`, the
requests made using :mod:`.requests` will be shown as ``curl`` commands without
any further modifications to the existing code, if any. See :class:`.Session`
for more details.

Attention:
    This is not real-time output. The simulation takes place after the request
    finishes, because it needs the :class:`requests.Response` object.
"""

import json
import requests

from curlify import to_curl
from typing import Callable, Iterable

from iripau.subprocess import TeeStreams, Popen


def raw_content(response: requests.Response) -> bytes:
    """ Just return the content of a response, either a string or bytes, without
        any post-processing.

        Hint:
            This function can be used as the value for the ``output_processor``
            argument in :func:`.curlify` or :class:`.Session`.

        Args:
            response: The result of performing a request.

        Returns:
            ``response.content`` as is.
    """
    return response.content


def hide_content(response: requests.Response) -> bytes:
    """ Always return ``***`` as bytes.

        Hint:
            This function can be used as the value for the ``output_processor``
            argument in :func:`.curlify` or :class:`.Session`.

        Args:
            response: The result of performing a request.

        Returns:
            ``b"***"``
    """
    return b"***"


def try_json_content(response: requests.Response) -> bytes:
    """ Try to pretty-format the content of a response as JSON.
        If the content is not a valid JSON, return the raw content.

        Hint:
            This function can be used as the value for the ``output_processor``
            argument in :func:`.curlify` or :class:`.Session`.

        Args:
            response: The result of performing a request.

        Returns:
            The pretty JSON or the raw content.
    """
    try:
        return json.dumps(response.json(), indent=4).encode()
    except json.JSONDecodeError:
        return response.content


def curlify(
    response: requests.Response,
    compressed: bool = False, verify: bool = True, pretty: bool = False,
    output_processor: Callable[[requests.Response], str | bytes] = None,
    headers_to_hide: Iterable[str] = [],
    headers_to_omit: Iterable[str] = [],
    stdout_tees: TeeStreams = [], add_global_stdout_tees: bool = True,
    stderr_tees: TeeStreams = [], add_global_stderr_tees: bool = True,
    prompt_tees: TeeStreams = [], add_global_prompt_tees: bool = True,
    echo: bool = None
):
    """ Simulate the request was executed by a ``curl`` subprocess.
        The command and output can be echoed and/or sent to files as described
        in :func:`.subprocess.run` and :class:`.subprocess.Popen`.
        At the end of the ``curl`` command, a comment with the HTTP status code
        and reason will be added.

        Args:
            response: The result of performing a request.
            compressed: Whether or not the request used compressed data.
                If ``True``, the argument ``--compressed`` will be added to the
                ``curl`` command.
            verify: Whether or not the request disabled TLS certificate
                verification.
                If ``False``, the argument ``--insecure`` will be added to the
                ``curl`` command.
            pretty: Break the ``curl`` command into several lines.
            output_processor: The return value of this function will be used as
                the ``stdout`` of the ``curl`` command.
                The default is :func:`.raw_content`, which returns whatever
                the content of the response is.
            headers_to_hide: The value of these headers will be replaced with
                ``***`` in the final ``curl`` command.
                If the header was not used in the request, ignore it.
            headers_to_omit: These headers won't be in the final ``curl`` command.
                If the header was not used in the request, ignore it.
            stdout_tees: The same as in :class:`.subprocess.Popen`.
            stderr_tees: The same as in :class:`.subprocess.Popen`.
            prompt_tees: The same as in :class:`.subprocess.Popen`.
            add_global_stdout_tees: The same as in :class:`.subprocess.Popen`.
            add_global_stderr_tees: The same as in :class:`.subprocess.Popen`.
            add_global_prompt_tees: The same as in :class:`.subprocess.Popen`.
            echo: The same as in :class:`.subprocess.Popen`.

        Example:
            Perform a request and use the response to echo the simulated ``curl``
            command and its output into the terminal::

                import requests


                response = requests.get("https://dummyjson.com/test", verify=False)
                curlify(response, echo=True)

                # $ curl -H 'User-Agent: python-requests/2.32.3' -H 'Accept-Encoding: gzip, deflate' -H 'Accept: */*' -H 'Connection: keep-alive' https://dummyjson.com/test # 200 - OK
                # {"status":"ok","method":"GET"}

        Attention:
            :mod:`requests` might fill in some headers with deduced or default
            values for every request.

            I the example above, the headers ``User-Agent``, ``Accept-Encoding``,
            ``Accept`` and ``Connection``  were added by the original
            :mod:`requests` module.
    """
    request = response.request
    if headers_to_hide or headers_to_omit:
        request = request.copy()

        for header in headers_to_omit:
            if header in request.headers:
                del request.headers[header]

        for header in headers_to_hide:
            if header in request.headers:
                request.headers[header] = "***"

    if output_processor is None:
        output_processor = raw_content

    stdout = output_processor(response)
    if not stdout.endswith(b"\n"):
        stdout += b"\n"
    stderr = b""

    Popen.simulate(
        cmd=to_curl(request, compressed, verify, pretty),
        stdout=stdout,
        stderr=stderr,
        comment=f"{response.status_code} - {response.reason}",
        stdout_tees=stdout_tees,
        stderr_tees=stderr_tees,
        prompt_tees=prompt_tees,
        add_global_stdout_tees=add_global_stdout_tees,
        add_global_stderr_tees=add_global_stderr_tees,
        add_global_prompt_tees=add_global_prompt_tees,
        echo=echo
    )


class Session(requests.Session):
    """ A :class:`requests.Session` that accepts :func:`.curlify` arguments in
        the :meth:`.Session.request` method.

        Note:
            The constructor arguments are the same as in the base
            :class:`requests.Session`.

        Example:
            Echo the simulated ``curl`` command and its output into the terminal::

                session = Session()
                response = session.get("https://dummyjson.com/test", verify=False, echo=True)

                # $ curl -H 'User-Agent: python-requests/2.32.3' -H 'Accept-Encoding: gzip, deflate' -H 'Accept: */*' -H 'Connection: keep-alive' --insecure https://dummyjson.com/test # 200 - OK
                # {"status":"ok","method":"GET"}

        Example:
            Pass some headers to a request and echo the pretty ``curl``
            equivalent command into the terminal but hide the value of some
            headers and without showing other ones, such as the ones added
            automatically::

                headers = {
                    "Accept": "application/json",
                    "Authorization": "Bearer A_VERY_LONG_AND_SECRET_JWT_TOKEN",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Nintendo 3DS; U; ; en) Version/1.7412.EU"
                }

                session = Session()
                response = session.post(
                    "https://dummyjson.com/test",
                    headers=headers,
                    json={"field": "value"},
                    headers_to_hide=["Authorization", "API-Key"],
                    headers_to_omit=["Accept-Encoding", "Content-Type", "User-Agent"],
                    pretty=True,
                    echo=True
                )

                # $ curl -H 'Accept-Encoding: gzip, deflate' \\
                # >   -H 'Accept: application/json' \\
                # >   -H 'Connection: keep-alive' \\
                # >   -H 'Authorization: ***' \\
                # >   -d '{"field": "value"}' \\
                # >   https://dummyjson.com/test # 200 - OK
                # {"status":"ok","method":"POST"}

            In that example, the intention was to hide the header ``API-Key``,
            but it was not actually used in the request, so it simply gets ignored.

        Example:
            Print the content of the response as a prettified JSON string::

                session = Session()
                response = session.get(
                    "https://dummyjson.com/test",
                    headers_to_omit=[
                        "Accept",
                        "Accept-Encoding",
                        "Connection",
                        "Content-Length",
                        "Content-Type",
                        "User-Agent"
                    ],
                    output_processor=try_json_content,
                    echo=True
                )

                # $ curl https://dummyjson.com/test # 200 - OK
                # {
                #     "status": "ok",
                #     "method": "GET"
                # }


        Hint:
            The names of the headers are case-insensitive.
    """

    def request(
        self, *args, compressed=False, pretty=False,
        output_processor=None, headers_to_hide=[], headers_to_omit=[],
        stdout_tees=[], add_global_stdout_tees=True,
        stderr_tees=[], add_global_stderr_tees=True,
        prompt_tees=[], add_global_prompt_tees=True,
        echo=None, **kwargs
    ) -> requests.Response:
        """ Constructs a :class:`requests.Request`, prepares it and sends it.
            The :func:`.curlify` arguments can also be used here as well as in
            the methods for the specific HTTP methods:

            * :meth:`.Session.delete`
            * :meth:`.Session.get`
            * :meth:`.Session.head`
            * :meth:`.Session.options`
            * :meth:`.Session.patch`
            * :meth:`.Session.post`
            * :meth:`.Session.put`

            Args:
                compressed: The same as in :func:`.curlify`.
                pretty: The same as in :func:`.curlify`.
                output_processor: The same as in :func:`.curlify`.
                headers_to_hide: The same as in :func:`.curlify`.
                headers_to_omit: The same as in :func:`.curlify`.
                stdout_tees: The same as in :class:`.subprocess.Popen`.
                stderr_tees: The same as in :class:`.subprocess.Popen`.
                prompt_tees: The same as in :class:`.subprocess.Popen`.
                add_global_stdout_tees: The same as in :class:`.subprocess.Popen`.
                add_global_stderr_tees: The same as in :class:`.subprocess.Popen`.
                add_global_prompt_tees: The same as in :class:`.subprocess.Popen`.
                echo: The same as in :class:`.subprocess.Popen`.
                *args: Passed to the base :meth:`requests.Session.request`.
                **kwargs: Passed to the base :meth:`requests.Session.request`.

            Returns:
                The result of performing a request.
        """
        response = super().request(*args, **kwargs)

        verify = kwargs.get("verify")
        if verify is None:
            verify = self.verify

        curlify(
            response, compressed, verify, pretty,
            output_processor, headers_to_hide, headers_to_omit,
            stdout_tees, add_global_stdout_tees,
            stderr_tees, add_global_stderr_tees,
            prompt_tees, add_global_prompt_tees,
            echo
        )
        return response


def delete(*args, **kwargs) -> requests.Response:
    """ Create a :class:`.Session`, call the DELETE HTTP method and return the result.
        The :func:`.curlify` arguments can also be used here.

        Args:
            *args: Passed to :meth:`.Session.delete`
            **kwargs: Passed to :meth:`.Session.delete`

        Returns:
            The result of performing a request.
    """
    return Session().delete(*args, **kwargs)


def get(*args, **kwargs) -> requests.Response:
    """ Create a :class:`.Session`, call the GET HTTP method and return the result.
        The :func:`.curlify` arguments can also be used here.

        Args:
            *args: Passed to :meth:`.Session.get`
            **kwargs: Passed to :meth:`.Session.get`

        Returns:
            The result of performing a request.
    """
    return Session().get(*args, **kwargs)


def head(*args, **kwargs) -> requests.Response:
    """ Create a :class:`.Session`, call the HEAD HTTP method and return the result.
        The :func:`.curlify` arguments can also be used here.

        Args:
            *args: Passed to :meth:`.Session.head`
            **kwargs: Passed to :meth:`.Session.head`

        Returns:
            The result of performing a request.
    """
    return Session().head(*args, **kwargs)


def options(*args, **kwargs) -> requests.Response:
    """ Create a :class:`.Session`, call the OPTIONS HTTP method and return the result.
        The :func:`.curlify` arguments can also be used here.

        Args:
            *args: Passed to :meth:`.Session.options`
            **kwargs: Passed to :meth:`.Session.options`

        Returns:
            The result of performing a request.
    """
    return Session().options(*args, **kwargs)


def patch(*args, **kwargs) -> requests.Response:
    """ Create a :class:`.Session`, call the PATCH HTTP method and return the result.
        The :func:`.curlify` arguments can also be used here.

        Args:
            *args: Passed to :meth:`.Session.patch`
            **kwargs: Passed to :meth:`.Session.patch`

        Returns:
            The result of performing a request.
    """
    return Session().patch(*args, **kwargs)


def post(*args, **kwargs) -> requests.Response:
    """ Create a :class:`.Session`, call the POST HTTP method and return the result.
        The :func:`.curlify` arguments can also be used here.

        Args:
            *args: Passed to :meth:`.Session.post`
            **kwargs: Passed to :meth:`.Session.post`

        Returns:
            The result of performing a request.
    """
    return Session().post(*args, **kwargs)


def put(*args, **kwargs) -> requests.Response:
    """ Create a :class:`.Session`, call the PUT HTTP method and return the result.
        The :func:`.curlify` arguments can also be used here.

        Args:
            *args: Passed to :meth:`.Session.put`
            **kwargs: Passed to :meth:`.Session.put`

        Returns:
            The result of performing a request.
    """
    return Session().put(*args, **kwargs)
