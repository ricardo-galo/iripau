"""
Tests to validate iripau.subprocess module
"""

import sys
import pytest
import subprocess

from mock import patch
from shlex import quote
from tempfile import SpooledTemporaryFile

from iripau.subprocess import DEVNULL
from iripau.subprocess import PIPE
from iripau.subprocess import STDOUT
from iripau.subprocess import FILE
from iripau.subprocess import Tee
from iripau.subprocess import Popen
from iripau.subprocess import TimeoutExpired
from iripau.subprocess import CalledProcessError
from iripau.subprocess import run
from iripau.subprocess import call
from iripau.subprocess import check_call
from iripau.subprocess import check_output
from iripau.subprocess import getoutput
from iripau.subprocess import getstatusoutput

KWARGS = {
    "stdin": DEVNULL,
    "capture_output": True,
    "text": True
}


def get_prompt_and_command(command, err2out=False, timeout=None):
    prompt = subprocess.run(
        "echo '' | bash -i 2>&1 1>/dev/null | head -1",
        shell=True,
        check=True,
        text=True,
        stdout=subprocess.PIPE
    ).stdout[:-1]

    if not isinstance(command, str):
        command = " ".join(map(quote, command))

    if err2out:
        command += " 2>&1"

    if timeout:
        command += f" # timeout={timeout}"

    return f"{prompt}{command}"


def read_file(file):
    file.seek(0)
    return file.read()


class TestSubprocess:

    def test_tee_stdout(self):
        with pytest.raises(ValueError):
            Tee(PIPE, [], STDOUT)

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_popen(self, echo, capfd):
        command = "echo $BASHPID; echo Sup!; sleep 1; echo Bye. >&2"
        stdout_tees = [
            SpooledTemporaryFile(mode="w+t"),
            SpooledTemporaryFile(mode="w+t"),
            SpooledTemporaryFile(mode="w+t")
        ]
        stderr_tees = [
            SpooledTemporaryFile(mode="w+t"),
            SpooledTemporaryFile(mode="w+t"),
            SpooledTemporaryFile(mode="w+t")
        ]
        prompt_tees = [
            SpooledTemporaryFile(mode="w+t"),
            SpooledTemporaryFile(mode="w+t"),
            SpooledTemporaryFile(mode="w+t")
        ]
        all_tee = SpooledTemporaryFile(mode="w+t")

        process = Popen(
            command,
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=PIPE,
            shell=True,
            executable="bash",
            echo=echo,
            stdout_tees=stdout_tees + [all_tee],
            stderr_tees=stderr_tees + [all_tee],
            prompt_tees=prompt_tees + [all_tee],
            text=True
        )

        with process:
            assert f"{process.pid}\n" == process.stdout.readline()
            stdout, stderr = process.communicate()

        assert "Sup!\n" == stdout
        assert "Bye.\n" == stderr

        expected_stdout = f"{process.pid}\nSup!\n"
        for file in stdout_tees:
            assert expected_stdout == read_file(file)

        expected_stderr = "Bye.\n"
        for file in stderr_tees:
            assert expected_stderr == read_file(file)

        expected_prompt = get_prompt_and_command(command) + "\n"
        for file in prompt_tees:
            assert expected_prompt == read_file(file)

        expected_output = expected_prompt + expected_stdout + expected_stderr
        assert expected_output == read_file(all_tee)

        out, err = capfd.readouterr()
        if echo:
            assert expected_prompt + expected_stdout == out
            assert expected_stderr == err
        else:
            assert "" == out == err

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_success(self, echo, capfd):
        command = ["echo", "Hello!"]
        output = run(command, echo=echo, **KWARGS)

        assert output.stdout == "Hello!\n"
        assert output.stderr == ""
        assert output.returncode == 0
        assert output.time > 0

        out, err = capfd.readouterr()
        if echo:
            assert get_prompt_and_command(command) + f"\n{output.stdout}" == out
            assert output.stderr == err
        else:
            assert "" == out == err

    def test_run_non_capturing_echo(self, capfd):
        command = ["echo", "Hello!"]
        output = run(command, stdout=None, stderr=None, echo=True)

        assert output.stdout is None
        assert output.stderr is None
        assert output.returncode == 0
        assert output.time > 0

        out, err = capfd.readouterr()
        assert get_prompt_and_command(command) + "\nHello!\n" == out
        assert "" == err

    @pytest.mark.parametrize("check", [False, True], ids=["no_check", "check"])
    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_error(self, echo, check, capfd):
        command = "echo Hello! >&2; exit 1"
        if check:
            with pytest.raises(CalledProcessError):
                run(command, shell=True, echo=echo, check=True)
        else:
            output = run(command, shell=True, echo=echo, **KWARGS)

            assert output.stdout == ""
            assert output.stderr == "Hello!\n"
            assert output.returncode == 1
            assert output.time > 0

            out, err = capfd.readouterr()
            if echo:
                assert get_prompt_and_command(command) + f"\n{output.stdout}" == out
                assert output.stderr == err
            else:
                assert "" == out == err

    def test_run_time(self):
        command = ["sleep", "3"]
        output = run(command)
        assert output.time > 3

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_timeout_and_terminate(self, echo, capfd):
        command = ["sleep", "3"]
        timeout = 1
        with pytest.raises(TimeoutExpired):
            run(command, timeout=timeout, echo=echo)

        if echo:
            out, err = capfd.readouterr()
            assert get_prompt_and_command(command, False, timeout) + "\n" == out
            assert "" == err

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_timeout_try_terminate_then_kill(self, echo, capfd):
        command = "trap '' TERM; sleep 3"
        timeout = 1
        with pytest.raises(TimeoutExpired):
            run(command, shell=True, timeout=timeout, echo=echo, sigterm_timeout=1)

        if echo:
            out, err = capfd.readouterr()
            assert get_prompt_and_command(command, False, timeout) + "\n" == out
            assert "" == err

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_timeout_and_kill(self, echo, capfd):
        command = "trap '' TERM; sleep 3"
        timeout = 1
        with pytest.raises(TimeoutExpired):
            run(command, shell=True, timeout=timeout, echo=echo, sigterm_timeout=0)

        if echo:
            out, err = capfd.readouterr()
            assert get_prompt_and_command(command, False, timeout) + "\n" == out
            assert "" == err

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_timeout_and_terminate_sudo(self, echo, capfd):
        command = ["sudo", "sudo", "sh", "-c",
                   "sudo sleep 30 | $(cat | (dd 2>/dev/null) | cat)"]
        timeout = 3
        with pytest.raises(TimeoutExpired):
            run(command, timeout=timeout, echo=echo)

        if echo:
            out, err = capfd.readouterr()
            assert get_prompt_and_command(command, False, timeout) + "\n" == out
            assert "" == err

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_timeout_try_terminate_then_kill_sudo(self, echo, capfd):
        command = "trap '' TERM; sudo sleep 30"
        timeout = 3
        with pytest.raises(TimeoutExpired):
            run(command, shell=True, timeout=timeout, echo=echo, sigterm_timeout=1)

        if echo:
            out, err = capfd.readouterr()
            assert get_prompt_and_command(command, False, timeout) + "\n" == out
            assert "" == err

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_timeout_and_kill_sudo(self, echo, capfd):
        command = "trap '' TERM; sudo sleep 30"
        timeout = 3
        with pytest.raises(TimeoutExpired):
            run(command, shell=True, timeout=timeout, echo=echo, sigterm_timeout=0)

        if echo:
            out, err = capfd.readouterr()
            assert get_prompt_and_command(command, False, timeout) + "\n" == out
            assert "" == err

    @pytest.mark.parametrize("text", [False, True], ids=["binary", "text"])
    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_input(self, echo, text, capfd):
        if text:
            encoder = decoder = lambda x: x
        else:
            encoder = str.encode
            decoder = bytes.decode
        command = "cat"
        input = "Some input"
        output = run(
            command,
            echo=echo,
            input=encoder(input),
            text=text,
            capture_output=True
        )

        assert output.stdout == encoder(input)
        assert output.stderr == encoder("")
        assert output.returncode == 0
        assert output.time > 0

        out, err = capfd.readouterr()
        if echo:
            assert get_prompt_and_command(command) + f"\n{decoder(output.stdout)}" == out
            assert output.stderr == encoder(err)
        else:
            assert "" == out == err

    @pytest.mark.parametrize("manual_echo", [False, True], ids=["no_manual_echo", "manual_echo"])
    @pytest.mark.parametrize("extra_tees", [0, 1, 3], ids=["no_extra", "one_extra", "few_extra"])
    @pytest.mark.parametrize("stderr", [None, STDOUT], ids=["no_redirect", "redirect"])
    @pytest.mark.parametrize("stdout", [None, PIPE, FILE], ids=["no_capture", "pipe", "file"])
    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    @pytest.mark.parametrize("simulation", [False, True], ids=["reality", "simulation"])
    def test_run_tee(self, simulation, echo, stdout, stderr, extra_tees, manual_echo, capfd):
        redirect = stderr is STDOUT
        stdout_command = "echo This goes to stdout"
        stderr_command = "echo This goes to stderr >&2"

        count = extra_tees - 1 if extra_tees > 1 else extra_tees
        prompt_tees = {SpooledTemporaryFile(mode="w+t") for _ in range(count)}
        stdout_tees = {SpooledTemporaryFile(mode="w+t") for _ in range(count)}
        stderr_tees = {SpooledTemporaryFile(mode="w+t") for _ in range(count)}
        all_tees = {SpooledTemporaryFile(mode="w+t") for _ in range(extra_tees - count)}

        # Ensure we are sending the intended number of files
        assert extra_tees == len(prompt_tees) + len(all_tees)
        assert extra_tees == len(stdout_tees) + len(all_tees)
        assert extra_tees == len(stderr_tees) + len(all_tees)

        if manual_echo:
            prompt_tees.add(sys.stdout)
            stdout_tees.add(sys.stdout)
            stderr_tees.add(sys.stderr)

        kwargs = {
            "text": True,
            "echo": echo,
            "stdout_tees": stdout_tees | all_tees,
            "stderr_tees": stderr_tees | all_tees,
            "prompt_tees": prompt_tees | all_tees
        }

        expected_stdout_command_prompt = get_prompt_and_command(stdout_command, redirect) + "\n"
        expected_stderr_command_prompt = get_prompt_and_command(stderr_command, redirect) + "\n"
        expected_prompt = expected_stdout_command_prompt + expected_stderr_command_prompt
        expected_output = (
            expected_stdout_command_prompt + "This goes to stdout\n" +
            expected_stderr_command_prompt + "This goes to stderr\n"
        )

        if redirect:
            expected_stdout = "This goes to stdout\nThis goes to stderr\n"
            expected_stderr = ""
            if echo or manual_echo:
                expected_captured_stdout = expected_output
            elif stdout is None:
                expected_captured_stdout = "" if simulation else expected_stdout
            else:
                expected_captured_stdout = ""
            expected_captured_stderr = ""
        else:
            expected_stdout = "This goes to stdout\n"
            expected_stderr = "This goes to stderr\n"
            if echo or manual_echo:
                expected_captured_stdout = (
                    expected_stdout_command_prompt + "This goes to stdout\n" +
                    expected_stderr_command_prompt
                )
                expected_captured_stderr = expected_stderr
            elif stdout is None:
                if simulation:
                    expected_captured_stdout = ""
                    expected_captured_stderr = ""
                else:
                    expected_captured_stdout = expected_stdout
                    expected_captured_stderr = expected_stderr
            else:
                expected_captured_stdout = ""
                expected_captured_stderr = "" if simulation else expected_stderr

        count = 1
        if simulation:
            fake_stdout_command = stdout_command
            fake_stderr_command = stderr_command
            fake_stdout_1 = "This goes to stdout\n"
            fake_stderr_1 = ""
            fake_stdout_2 = ""
            fake_stderr_2 = "This goes to stderr\n"
            if redirect:  # Simulate redirection
                fake_stdout_command += " 2>&1"
                fake_stderr_command += " 2>&1"
                fake_stdout_2, fake_stderr_2 = fake_stderr_2, fake_stdout_2

            for _ in range(count):
                Popen.simulate(fake_stdout_command, fake_stdout_1, fake_stderr_1, **kwargs)
                Popen.simulate(fake_stderr_command, fake_stdout_2, fake_stderr_2, **kwargs)
        else:
            expected_stdout_1 = expected_stderr_1 = expected_stdout_2 = expected_stderr_2 = None
            if stdout is not None:
                expected_stdout_1 = "This goes to stdout\n"
                expected_stdout_2 = "This goes to stderr\n" if redirect else ""

            for _ in range(count):
                output = run(stdout_command, stdout=stdout, stderr=stderr, shell=True, **kwargs)
                assert expected_stdout_1 == output.stdout
                assert expected_stderr_1 == output.stderr

                output = run(stderr_command, stdout=stdout, stderr=stderr, shell=True, **kwargs)
                assert expected_stdout_2 == output.stdout
                assert expected_stderr_2 == output.stderr

        expected_content = expected_stdout * count
        for file in stdout_tees - {sys.stdout}:
            assert expected_content == read_file(file)

        expected_content = expected_stderr * count
        for file in stderr_tees - {sys.stderr}:
            assert expected_content == read_file(file)

        expected_content = expected_prompt * count
        for file in prompt_tees - {sys.stdout}:
            assert expected_content == read_file(file)

        expected_content = expected_output * count
        for file in all_tees:
            assert expected_content == read_file(file)

        out, err = capfd.readouterr()
        assert expected_captured_stdout * count == out
        assert expected_captured_stderr * count == err

    @pytest.mark.parametrize("echo", [False, True], ids=["no_echo", "echo"])
    def test_run_alias(self, echo, capfd):
        command = ["echo", "-ne", "Hello!\\tBye."]
        alias = ["echo", "Hello!\\tBye."]
        output = run(command, echo=echo, alias=alias, **KWARGS)

        assert output.stdout == "Hello!\tBye."
        assert output.stderr == ""
        assert output.returncode == 0
        assert output.time > 0

        out, err = capfd.readouterr()
        if echo:
            assert get_prompt_and_command(alias) + f"\n{output.stdout}" == out
            assert output.stderr == err
        else:
            assert "" == out == err

    @patch("iripau.subprocess.run")
    def test_call(self, mock_run):
        returncode = call("arg1", "arg2", kwarg1="kwarg1")

        mock_run.assert_called_once_with("arg1", "arg2", kwarg1="kwarg1")
        assert mock_run.return_value.returncode == returncode

    @patch("iripau.subprocess.run")
    def test_check_call(self, mock_run):
        check_call("arg1", "arg2", kwarg1="kwarg1")

        mock_run.assert_called_once_with(
            "arg1",
            "arg2",
            kwarg1="kwarg1",
            check=True
        )

    @patch("iripau.subprocess.run")
    def test_check_output(self, mock_run):
        stdout = check_output("arg1", "arg2", kwarg1="kwarg1")

        mock_run.assert_called_once_with(
            "arg1",
            "arg2",
            kwarg1="kwarg1",
            check=True,
            stdout=PIPE
        )
        assert mock_run.return_value.stdout == stdout

    @patch("iripau.subprocess.run")
    def test_getoutput(self, mock_run):
        stdout = getoutput("arg1", "arg2", kwarg1="kwarg1")

        mock_run.assert_called_once_with(
            "arg1",
            "arg2",
            kwarg1="kwarg1",
            stdout=PIPE,
            stderr=STDOUT,
            shell=True,
            text=True
        )
        assert mock_run.return_value.stdout == stdout

    @patch("iripau.subprocess.run")
    def test_getstatusoutput(self, mock_run):
        returncode, stdout = getstatusoutput("arg1", "arg2", kwarg1="kwarg1")

        mock_run.assert_called_once_with(
            "arg1",
            "arg2",
            kwarg1="kwarg1",
            stdout=PIPE,
            stderr=STDOUT,
            shell=True,
            text=True
        )
        assert mock_run.return_value.returncode == returncode
        assert mock_run.return_value.stdout == stdout
