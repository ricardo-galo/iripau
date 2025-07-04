"""
A wrapper of the requests module
"""

import requests

from curlify import to_curl

from iripau.subprocess import TeeStreams, Popen


def process_output(response):
    return response.content


def curlify(
    response, compressed=False, verify=True, pretty=False,
    output_processor=None, headers_to_hide=[], headers_to_omit=[],
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

    if output_processor is None:
        output_processor = process_output

    stdout = output_processor(response)
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
        output_processor=None, headers_to_hide=[], headers_to_omit=[],
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
            output_processor, headers_to_hide, headers_to_omit,
            stdout_tees, add_global_stdout_tees,
            stderr_tees, add_global_stderr_tees,
            prompt_tees, add_global_prompt_tees,
            echo
        )
        return response


def delete(*args, **kwargs):
    return Session().delete(*args, **kwargs)


def get(*args, **kwargs):
    return Session().get(*args, **kwargs)


def head(*args, **kwargs):
    return Session().head(*args, **kwargs)


def options(*args, **kwargs):
    return Session().options(*args, **kwargs)


def patch(*args, **kwargs):
    return Session().patch(*args, **kwargs)


def post(*args, **kwargs):
    return Session().post(*args, **kwargs)


def put(*args, **kwargs):
    return Session().put(*args, **kwargs)
