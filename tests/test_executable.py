"""
Tests to validate iripau.executable module
"""

from mock import MagicMock, patch, call

from iripau.executable import Command
from iripau.executable import Executable


class TestExecutable:

    def test_command_call(self):
        parent = MagicMock()
        command = "group"

        group = Command(parent, command)
        parent._mk_command.assert_called_once_with(command)

        output = group("list", color="auto")

        parent.assert_called_once_with(
            parent._mk_command.return_value,
            "list",
            color="auto"
        )
        assert output == parent.return_value

    @patch("iripau.executable.Command")
    def test_command_subcommand(self, mock_command):
        parent = MagicMock()
        command = "group"

        group = Command(parent, command)
        group_install = group.install

        mock_command.assert_called_once_with(group, "install")
        assert group_install == group.install
        mock_command.assert_called_once()

    @patch("iripau.executable.choice")
    @patch("iripau.executable.host_run")
    def test_executable_call(self, mock_run, mock_choice):
        executable = "dnf"
        commands_map = {"check_update": "check-update"}
        options_map = {
            "config": ("-c", "--config"),
            "quiet": ("-q", "--quiet"),
            "skip_broken": ("--skip-broken",)
        }

        mock_choice.side_effect = lambda options: options[0]
        dnf = Executable(executable, commands_map.get, options_map.get)
        output = dnf(
            "group", "install", "Development Tools",
            config="/tmp/dnf.conf", quiet=None, skip_broken=True
        )
        assert output == mock_run.return_value

        expected_choice_calls = [
            call(("-c", "--config")),
            call(("--skip-broken",))
        ]

        mock_choice.assert_has_calls(expected_choice_calls)
        tokens = [
            "dnf",
            "group",
            "install",
            "Development Tools",
            "-c", "/tmp/dnf.conf",
            "--skip-broken"
        ]
        mock_run.assert_called_once_with(tokens)

    @patch("iripau.executable.choice")
    @patch("iripau.executable.host_run")
    def test_executable_append_arguments(self, mock_run, mock_choice):
        executable = "docker"
        options_map = {
            "volume": ("-v", "--volume"),
            "name": ("--name",),
            "privileged": ("--privileged",)
        }

        mock_choice.side_effect = lambda options: options[-1]
        docker = Executable(executable, make_option=options_map.get)
        output = docker.run(
            "ubuntu:latest",
            volume=["/tmp/data:/data", "/home/user/repos:/root/Repos:Z"],
            privileged=True,
            name="ubuntu-dev"
        )
        assert output == mock_run.return_value

        expected_choice_calls = [
            call(("-v", "--volume")),
            call(("--privileged",)),
            call(("--name",))
        ]

        mock_choice.assert_has_calls(expected_choice_calls)
        tokens = [
            "docker",
            "run",
            "ubuntu:latest",
            "--volume=/tmp/data:/data",
            "--volume=/home/user/repos:/root/Repos:Z",
            "--privileged",
            "--name=ubuntu-dev"
        ]
        mock_run.assert_called_once_with(tokens)

    @patch("iripau.executable.host_run")
    def test_executable_host_run_args(self, mock_run):
        executable = "dnf"

        dnf = Executable(executable)
        dnf(_timeout=5)

        mock_run.assert_called_once_with(["dnf"], timeout=5)

    @patch("iripau.executable.host_run")
    def test_executable_alias(self, mock_run):
        executable = "ls -al"

        ls = Executable(executable, alias="ll")
        ls("/tmp")

        mock_run.assert_called_once_with(
            ["ls", "-al", "/tmp"],
            alias=["ll", "/tmp"]
        )

    @patch("iripau.executable.host_run")
    def test_executable_default_underscore_to_dash(self, mock_run):
        executable = "git"

        git = Executable(executable)
        git.format_patch(interdiff="feature/v1", no_attach=True, signature_file="some/path")

        mock_run.assert_called_once_with(
            ["git", "format-patch", "--interdiff=feature/v1",
             "--no-attach", "--signature-file=some/path"]
        )
