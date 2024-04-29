"""
Utilities for the requests module
"""

import requests

from curlify import to_curl

from iripau.subprocess import TeeStreams, Popen


def curlify(
    response, compressed=False, verify=True, pretty=False,
    hide_output=False, headers_to_hide=[], headers_to_omit=[],
    stdout_tees: TeeStreams = [], add_global_stdout_tees=True,
    stderr_tees: TeeStreams = [], add_global_stderr_tees=True,
    prompt_tees: TeeStreams = [], add_global_prompt_tees=True,
    echo=None
):
    """ Simulate the request was executed by a curl subprocess.
        The command and output can be echoed and/or sent to files as described
        in subprocess.run
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

    stdout = hide_output and b"***" or response.content
    if not stdout.endswith(b"\n"):
        stdout += b"\n"
    stderr = ""

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
    """ A requests.Session that accepts curlify arguments in the request method """

    def request(
        self, *args, compressed=False, pretty=False,
        hide_output=False, headers_to_hide=[], headers_to_omit=[],
        stdout_tees: TeeStreams = [], add_global_stdout_tees=True,
        stderr_tees: TeeStreams = [], add_global_stderr_tees=True,
        prompt_tees: TeeStreams = [], add_global_prompt_tees=True,
        echo=None, **kwargs
    ):
        response = super().request(*args, **kwargs)

        verify = kwargs.get("verify")
        if verify is None:
            verify = self.verify

        curlify(
            response, compressed, verify, pretty,
            hide_output, headers_to_hide, headers_to_omit,
            stdout_tees, add_global_stdout_tees,
            stderr_tees, add_global_stderr_tees,
            prompt_tees, add_global_prompt_tees,
            echo
        )
        return response
