"""
Tests to validate iripau.command module
"""

import os
import pytest

from mock import patch
from shlex import quote
from socket import gethostname
from getpass import getuser

from iripau.command import _solve_ssh_users
from iripau.command import user_cmd
from iripau.command import local_run
from iripau.command import local_run_interactive
from iripau.command import ssh_run
from iripau.command import ssh_run_interactive
from iripau.command import host_run
from iripau.command import host_run_interactive

from iripau.subprocess import DEVNULL

ROWS = os.popen("tput lines").read().rstrip()
COLS = os.popen("tput cols").read().rstrip()
STTY_CMD = "stty rows {0} cols {1} && ".format(ROWS, COLS)
HOSTNAME = gethostname()
USER = getuser()
KWARGS = {"kwarg1": "arg1", "kwarg2": 2, "kwarg3": "Sup!", "kwarg4": 4}


def run_kwargs(
    args, *, executable=None, stdin=None, stdout=None, stderr=None, shell=False,
    cwd=None, env=None, user=None, encoding=None, errors=None, text=True,
    stdout_tees=[], add_global_stdout_tees=True,
    stderr_tees=[], add_global_stderr_tees=True,
    prompt_tees=[], add_global_prompt_tees=True,
    echo=None, alias=None, input=None, capture_output=False,
    timeout=120, check=False, sigterm_timeout=10
):
    return locals()


class TestCommand:

    @patch("iripau.command.USER", new="current-user")
    def test_solve_ssh_users(self):
        assert ("current-user", "host1") == \
            _solve_ssh_users("host1", None)

        assert ("current-user", "host1") == \
            _solve_ssh_users("host1", "current-user")

        assert ("other-user", "host1") == \
            _solve_ssh_users("host1", "other-user")

        assert ("current-user", "host1") == \
            _solve_ssh_users("current-user@host1", None)

        assert ("current-user", "host1") == \
            _solve_ssh_users("current-user@host1", "current-user")

        assert ("current-user", "current-user@host1") == \
            _solve_ssh_users("current-user@host1", "other-user")

        assert ("other-user", "other-user@host1") == \
            _solve_ssh_users("other-user@host1", None)

        assert ("other-user", "other-user@host1") == \
            _solve_ssh_users("other-user@host1", "current-user")

        assert ("other-user", "host1") == \
            _solve_ssh_users("other-user@host1", "other-user")

    @pytest.mark.parametrize("env", [None, {"FOO": "foo", "BAR": "bar"}], ids=["no_env", "env"])
    @pytest.mark.parametrize("alias_type", [None, list, str])
    @pytest.mark.parametrize("cmd_type", [list, str])
    @pytest.mark.parametrize("user", ["no_user", "current-user", "other-user", "root"])
    @patch("iripau.command.USER", new="current-user")
    def test_user_cmd(self, user, cmd_type, alias_type, env):
        if user == "no_user":
            user = None

        env_tokens = list(map("{0[0]}={0[1]}".format, (env or {}).items()))
        alias = {
            str: "echo bye",
            list: ["echo", "bye"],
            None: None
        }[alias_type]
        if cmd_type is str:
            cmd = "whoami; sleep 1 && echo Bye!"
            internal_alias = {
                str: ["sh", "-c", alias],
                list: alias,
                None: ["sh", "-c", cmd]
            }[alias_type]
            expected_cmds = {
                None: (
                    cmd,
                    alias
                ),
                "current-user": (
                    cmd,
                    alias
                ),
                "other-user": (
                    ["sudo", "-Eu", user] + env_tokens + ["sh", "-c", cmd],
                    ["sudo", "-Eu", user] + internal_alias
                ),
                "root": (
                    ["sudo", "-E"] + env_tokens + ["sh", "-c", cmd],
                    ["sudo", "-E"] + internal_alias
                )
            }
        else:
            cmd = ["echo", "Hello!", "Bye!"]
            internal_alias = {
                str: ["sh", "-c", alias],
                list: alias,
                None: cmd
            }[alias_type]
            expected_cmds = {
                None: (
                    cmd,
                    alias
                ),
                "current-user": (
                    cmd,
                    alias
                ),
                "other-user": (
                    ["sudo", "-Eu", user] + env_tokens + cmd,
                    ["sudo", "-Eu", user] + internal_alias
                ),
                "root": (
                    ["sudo", "-E"] + env_tokens + cmd,
                    ["sudo", "-E"] + internal_alias
                )
            }
        assert expected_cmds[user] == user_cmd(user, cmd, alias, env)

    @pytest.mark.parametrize("env", [None, {"FOO": "foo", "BAR": "bar"}], ids=["no_env", "env"])
    @pytest.mark.parametrize("cmd_type", [list, str])
    @pytest.mark.parametrize("user", ["no_user", "root", "no-root"])
    @patch("iripau.command.USER", new="root")
    def test_user_cmd_being_root(self, user, cmd_type, env):
        if user == "no_user":
            user = None

        env_tokens = list(map("{0[0]}={0[1]}".format, (env or {}).items()))
        if cmd_type is str:
            cmd = "whoami; sleep 1 && echo Bye!"
            expected_cmds = {
                None: (cmd, None),
                "root": (cmd, None),
                "no-root": (
                    ["sudo", "-Eu", user] + env_tokens + ["sh", "-c", cmd],
                    ["sudo", "-Eu", user, "sh", "-c", cmd]
                )
            }
        else:
            cmd = ["echo", "Hello!", "Bye!"]
            expected_cmds = {
                None: (cmd, None),
                "root": (cmd, None),
                "no-root": (
                    ["sudo", "-Eu", user] + env_tokens + cmd,
                    ["sudo", "-Eu", user] + cmd
                )
            }
        assert expected_cmds[user] == user_cmd(user, cmd, None, env)

    @pytest.mark.parametrize("cmd_type", [list, str])
    @patch("iripau.subprocess.run")
    def test_local_run(self, mock_run, cmd_type):
        cmd = "echo Hello!" if cmd_type is str else ["echo", "Hello!"]

        output = local_run(cmd)

        mock_run.assert_called_once_with(
            **run_kwargs(cmd, shell=cmd_type is str, stdin=DEVNULL, capture_output=True)
        )
        assert mock_run.return_value == output

    @pytest.mark.parametrize("env", [None, {"FOO": "foo", "BAR": "bar"}], ids=["no_env", "env"])
    @pytest.mark.parametrize("cmd_type", [list, str])
    @patch("iripau.command.spawn")
    def test_local_run_interactive(self, mock_spawn, cmd_type, env):
        cmd = "bash -i" if cmd_type is str else ["bash", "-i"]

        result = local_run_interactive(cmd, env=env)

        if cmd_type is list:
            cmd = " ".join(quote(token) for token in cmd)
        cmd = STTY_CMD + cmd
        if env:
            env_tokens = list(map("{0[0]}={0[1]}".format, env.items()))
            cmd = "export " + " ".join(env_tokens) + " && " + cmd
        mock_spawn.assert_called_once_with(["sh", "-ic", cmd])
        assert mock_spawn.return_value == result

    @pytest.mark.parametrize("ssh_password", [None, "a_password"], ids=["no_ssh_pass", "ssh_pass"])
    @pytest.mark.parametrize("ssh_args", [[], ["-O", "exit"]], ids=["no_ssh_args", "ssh_args"])
    @pytest.mark.parametrize("env", [None, {"FOO": "foo", "BAR": "bar"}], ids=["no_env", "env"])
    @pytest.mark.parametrize("cwd", [None, "/some/path"], ids=["no_cwd", "cwd"])
    @pytest.mark.parametrize("cmd_type", [list, str])
    @patch("iripau.subprocess.run")
    def test_ssh_run(self, mock_run, cmd_type, cwd, env, ssh_args, ssh_password):
        host = "user@host"
        cmd = "echo Hello!" if cmd_type is str else ["echo", "Hello!"]

        output = ssh_run(
            host,
            cmd,
            cwd=cwd, env=env,
            ssh_args=ssh_args,
            ssh_password=ssh_password
        )

        if cmd_type is not str:
            cmd = " ".join(map(quote, cmd))
        alias = ["ssh", host, cmd]
        if cwd:
            cmd = "cd /some/path && " + cmd
        if env:
            cmd = "export FOO=foo BAR=bar && " + cmd
        ssh_cmd = ["ssh"] + ssh_args + [host, cmd]

        if ssh_password:
            ssh_cmd = ["sshpass", "-p", ssh_password] + ssh_cmd

        mock_run.assert_called_once_with(
            **run_kwargs(ssh_cmd, shell=False, alias=alias, stdin=DEVNULL, capture_output=True)
        )
        assert mock_run.return_value == output

    @pytest.mark.parametrize("ssh_password", [None, "a_password"], ids=["no_ssh_pass", "ssh_pass"])
    @pytest.mark.parametrize("ssh_args", [[], ["-O", "exit"]], ids=["no_ssh_args", "ssh_args"])
    @pytest.mark.parametrize("cmd_type", [list, str])
    @patch("iripau.command.spawn")
    def test_ssh_run_interactive(self, mock_spawn, cmd_type, ssh_args, ssh_password):
        host = "user@host"
        cmd = "bash -i" if cmd_type is str else ["bash", "-i"]

        result = ssh_run_interactive(
            host,
            cmd,
            ssh_args=ssh_args,
            ssh_password=ssh_password
        )

        if cmd_type is list:
            cmd = " ".join(quote(token) for token in cmd)
        ssh_cmd = ["ssh", "-tt"] + ssh_args + [host, STTY_CMD + cmd]

        if ssh_password:
            ssh_cmd = ["sshpass", "-p", ssh_password] + ssh_cmd

        mock_spawn.assert_called_once_with(ssh_cmd)
        assert mock_spawn.return_value == result

    @pytest.mark.parametrize("host", ["localhost", HOSTNAME])
    @patch("iripau.command.ssh_args")
    @patch("iripau.command.local_args", return_value=KWARGS)
    @patch("iripau.subprocess.run")
    def test_host_run_local(self, mock_run, mock_local_args, mock_ssh_args, host):
        command = "echo Hello!"

        output = host_run(command, host=host)

        mock_local_args.assert_called_once_with(command)
        mock_ssh_args.assert_not_called()
        mock_run.assert_called_once_with(**KWARGS)
        assert mock_run.return_value == output

    @pytest.mark.parametrize("host", ["localhost", HOSTNAME])
    @patch("iripau.command.local_run_interactive")
    def test_host_run_interactive_local(self, mock_run, host):
        command = "echo Hello!"

        result = host_run_interactive(command, host=host)

        mock_run.assert_called_once_with(command)
        assert mock_run.return_value == result

    @patch("iripau.command.ssh_args", return_value=KWARGS)
    @patch("iripau.command.local_args")
    @patch("iripau.subprocess.run")
    def test_host_run_remote(self, mock_run, mock_local_args, mock_ssh_args):
        host = "user@host"
        command = "echo Hello!"

        output = host_run(command, host=host)

        mock_local_args.assert_not_called()
        mock_ssh_args.assert_called_once_with(
            host,
            command,
            ssh_user=None,
            ssh_password=None,
            ssh_args=[],
            add_global_ssh_args=True
        )
        mock_run.assert_called_once_with(**KWARGS)
        assert mock_run.return_value == output

    @patch("iripau.command.ssh_run_interactive")
    def test_host_run_interactive_remote(self, mock_run):
        host = "user@host"
        command = "echo Hello!"

        result = host_run_interactive(command, host=host)

        mock_run.assert_called_once_with(host, command, ssh_user=None)
        assert mock_run.return_value == result
