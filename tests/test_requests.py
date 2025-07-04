"""
Tests to validate iripau.requests module
"""

import pytest
import mock

from iripau.requests import Session
from iripau.requests import delete
from iripau.requests import get
from iripau.requests import head
from iripau.requests import options
from iripau.requests import patch
from iripau.requests import post
from iripau.requests import put

URL = "https://some.url.com:8080/api"
KWARGS = {
    "kwarg1": "Value-1",
    "kwarg2": "Value-2"
}


def hide_content(response):
    return b"***"


class TestRequests:

    @pytest.mark.parametrize("hide_output", [False, True], ids=["show_output", "hide_output"])
    @pytest.mark.parametrize("session_verify", [False, True], ids=["request", "session"])
    @pytest.mark.parametrize("verify", [False, True], ids=["insecure", "secure"])
    def test_curlify(self, verify, session_verify, hide_output, capfd):
        session = Session()

        if session_verify:
            session.verify = verify

        response = session.post(
            "https://dummyjson.com/test",
            verify=None if session_verify else verify,
            headers={
                "API-Key": "QWERTY123",
                "Accept": "application/json",
                "Authorization": "Bearer 23U746F5R23745RG78345EDR3"
            },
            data={
                "name": "The Name",
                "status": "Old$"
            },
            output_processor=hide_output and hide_content or None,
            headers_to_hide=["API-Key", "Authorization"],
            headers_to_omit=["User-Agent", "Accept-Encoding", "Connection"],
            echo=True
        )

        out, err = capfd.readouterr()
        if verify:
            assert "--insecure" not in out
        else:
            assert "--insecure" in out

        if hide_output:
            assert out.endswith("***\n")
        else:
            assert not out.endswith("***\n")

        # Omitted headers
        assert "-H 'Accept: application/json'" in out
        assert "-H 'API-Key: ***'" in out
        assert "-H 'Authorization: ***'" in out

        # Hidden headers
        assert "-H 'Accept-Encoding: gzip, deflate'" not in out
        assert "-H 'Connection: keep-alive'" not in out
        assert "-H 'User-Agent: python-requests/2.32.3'" not in out

        # Because of using data argument in the request
        assert "-H 'Content-Type: application/x-www-form-urlencoded'" in out
        assert "-d 'name=The+Name&status=Old%24'" in out

        assert not err

        # The request object was not touched
        assert "Accept-Encoding" in response.request.headers
        assert "Connection" in response.request.headers
        assert "User-Agent" in response.request.headers

        assert response.request.headers["API-Key"] != "***"
        assert response.request.headers["Authorization"] != "***"

    @mock.patch("iripau.requests.Session")
    def test_delete(self, mock_session):
        response = delete(URL, **KWARGS)
        mock_session.return_value.delete.assert_called_once_with(URL, **KWARGS)
        assert mock_session.return_value.delete.return_value == response

    @mock.patch("iripau.requests.Session")
    def test_get(self, mock_session):
        response = get(URL, **KWARGS)
        mock_session.return_value.get.assert_called_once_with(URL, **KWARGS)
        assert mock_session.return_value.get.return_value == response

    @mock.patch("iripau.requests.Session")
    def test_head(self, mock_session):
        response = head(URL, **KWARGS)
        mock_session.return_value.head.assert_called_once_with(URL, **KWARGS)
        assert mock_session.return_value.head.return_value == response

    @mock.patch("iripau.requests.Session")
    def test_options(self, mock_session):
        response = options(URL, **KWARGS)
        mock_session.return_value.options.assert_called_once_with(URL, **KWARGS)
        assert mock_session.return_value.options.return_value == response

    @mock.patch("iripau.requests.Session")
    def test_patch(self, mock_session):
        response = patch(URL, **KWARGS)
        mock_session.return_value.patch.assert_called_once_with(URL, **KWARGS)
        assert mock_session.return_value.patch.return_value == response

    @mock.patch("iripau.requests.Session")
    def test_post(self, mock_session):
        response = post(URL, **KWARGS)
        mock_session.return_value.post.assert_called_once_with(URL, **KWARGS)
        assert mock_session.return_value.post.return_value == response

    @mock.patch("iripau.requests.Session")
    def test_put(self, mock_session):
        response = put(URL, **KWARGS)
        mock_session.return_value.put.assert_called_once_with(URL, **KWARGS)
        assert mock_session.return_value.put.return_value == response
