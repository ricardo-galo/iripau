"""
Tests to validate iripau.requests module
"""

import pytest

from iripau.requests import Session


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
            hide_output=hide_output,
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
