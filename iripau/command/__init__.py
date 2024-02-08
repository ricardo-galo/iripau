"""
Extension to the subprocess module to execute commands in different ways

This module relies on the following system utilities being installed:
* sh
* ssh
* sshpass
* stty
* sudo
"""

import io
import os
import shlex
import psutil

from pty import spawn
from typing import Iterable
from socket import gethostname
from getpass import getuser

from iripau import subprocess
from iripau.subprocess import quote

GLOBAL_SSH_ARGS = []
TIMEOUT = 120
USER = getuser()

LOCALHOSTS = {None, "localhost", gethostname()} | {
    addr.address
    for nic in psutil.net_if_addrs().values()
    for addr in nic
    if addr.family.name == "AF_INET"
}


def _stty(cmd):
    """ Prepend to 'cmd' the stty command to set the terminal size to the current one """
    if not isinstance(cmd, str):
        cmd = quote(cmd)
    rows, cols = os.popen("tput lines; tput cols").read().split()
    return f"stty rows {rows} cols {cols} && {cmd}"


def _env(env, user):
    if env and user in {USER, None}:
        envs = dict(os.environ)
        envs.update(env)
        return envs


def _parse_host(host):
    splits = host.split("@", maxsplit=1)
    if len(splits) == 1:
        splits = [None] + splits
    return tuple(splits)


def _solve_ssh_users(host, local_user):
    remote_user, parsed_host = _parse_host(host)
    local_user = local_user or USER
    remote_user = remote_user or local_user
    if remote_user == local_user:
        host = parsed_host
    return remote_user, host


def _shell_envs(env):
    """ Return a list of shell env vars """
    return [f"{key}={value}" for key, value in env.items()]


def _is_localhost(host):
    return host.split("@", maxsplit=1)[-1] in LOCALHOSTS


def user_cmd(user, cmd, alias=None, env=None, current=None):
    """ Return the final cmd so that the original cmd gets executed as the desired
        user. Same thing for alias.

        Assume current user has password-less sudo.

        Return the updated cmd and alias.
    """
    if user in {current or USER, None}:
        return cmd, alias

    if isinstance(cmd, str):
        cmd = ["sh", "-c", cmd]

    if alias:
        if isinstance(alias, str):
            alias = ["sh", "-c", alias]
    else:
        alias = cmd

    env = _shell_envs(env or {})
    prefix = ["sudo", "-E"] if user == "root" else ["sudo", "-Eu", user]
    return prefix + env + cmd, prefix + alias


def local_args(
    args, *, executable=None, stdin=None, stdout=None, stderr=None, cwd=None,
    env=None, user=None, encoding=None, errors=None, text=True,
    stdout_tees: Iterable[io.IOBase] = [], add_global_stdout_tees=True,
    stderr_tees: Iterable[io.IOBase] = [], add_global_stderr_tees=True,
    prompt_tees: Iterable[io.IOBase] = [], add_global_prompt_tees=True,
    echo=None, alias=None, input=None, capture_output=False,
    timeout=TIMEOUT, check=False, sigterm_timeout=10
):
    """ Return the subprocess.run kwargs for a command to be run locally """
    if stdout is None and stderr is None:
        capture_output = True
    if input is None:
        stdin = subprocess.DEVNULL

    args, alias = user_cmd(user, args, alias, env)
    shell = isinstance(args, str)
    env = _env(env, user)
    return locals()


def local_run(*args, **kwargs):
    kwargs = local_args(*args, **kwargs)
    return subprocess.run(**kwargs)


def local_run_interactive(cmd, *args, env=None, user=None, **kwargs):
    cmd = _stty(cmd)
    if env and user in {USER, None}:
        env = quote(_shell_envs(env))
        cmd = f"export {env} && {cmd}"
    cmd, _ = user_cmd(user, ["sh", "-ic", cmd])
    return spawn(cmd, *args, **kwargs)


def set_global_ssh_args(*args):
    GLOBAL_SSH_ARGS[:] = list(args)


def shell_cmd(cmd, alias=None, user=None, cwd=None, env=None):
    """ Return the final cmd so that the original cmd can be executed in the
        shell. Same thing for alias.

        Return the updated cmd and alias.
    """
    if not isinstance(cmd, str):
        cmd = quote(cmd)
    alias = alias or cmd
    if not isinstance(alias, str):
        alias = quote(alias)
    if cwd:
        cmd = f"cd {shlex.quote(cwd)} && {cmd}"
    if env and user in {USER, None}:
        env = quote(_shell_envs(env))
        cmd = f"export {env} && {cmd}"
    return cmd, alias


def ssh_cmd(host, cmd, alias=None, user=None, cwd=None, env=None, args=[], password=None):
    """ Return the final cmd so that the original cmd can be executed through
        shs. Same thing for alias.

        Return the updated cmd and alias.
    """
    cmd, alias = shell_cmd(cmd, alias, user, cwd, env)
    cmd = ["ssh"] + args + [host, cmd]
    alias = ["ssh", host, alias]
    if password:
        cmd = ["sshpass", "-p", password] + cmd
    return cmd, alias


def ssh_args(
    host, cmd, cwd=None, env=None, user=None, alias=None,
    ssh_user=None, ssh_password=None, ssh_args=[], add_global_ssh_args=True,
    **kwargs
):
    """ Return the subprocess.run kwargs for a command to be run through ssh """
    remote_user, host = _solve_ssh_users(host, ssh_user)
    cmd, alias = user_cmd(user, cmd, alias, env, remote_user)
    if add_global_ssh_args:
        ssh_args += GLOBAL_SSH_ARGS
    cmd, alias = ssh_cmd(host, cmd, alias, user, cwd, env, ssh_args, ssh_password)
    return local_args(cmd, alias=alias, user=ssh_user, **kwargs)


def ssh_run(*args, **kwargs):
    kwargs = ssh_args(*args, **kwargs)
    return subprocess.run(**kwargs)


def ssh_run_interactive(
    host, cmd, *args, env=None, user=None,
    ssh_user=None, ssh_password=None, ssh_args=[], add_global_ssh_args=True,
    **kwargs
):
    remote_user, host = _solve_ssh_users(host, ssh_user)
    cmd, _ = user_cmd(user, _stty(cmd), None, env, remote_user)
    ssh_args = ["-tt"] + ssh_args
    if add_global_ssh_args:
        ssh_args += GLOBAL_SSH_ARGS
    cmd, _ = ssh_cmd(host, cmd, None, user, None, env, ssh_args, ssh_password)
    cmd, _ = user_cmd(ssh_user, cmd)
    return spawn(cmd, *args, **kwargs)


def host_args(
    cmd, host="localhost",
    ssh_user=None, ssh_password=None, ssh_args=[], add_global_ssh_args=True,
    **kwargs
):
    """ Return the subprocess.run kwargs for a command to be run in any host """
    if _is_localhost(host):
        return local_args(cmd, **kwargs)
    return globals()["ssh_args"](
        host, cmd,
        ssh_user=ssh_user,
        ssh_password=ssh_password,
        ssh_args=ssh_args,
        add_global_ssh_args=add_global_ssh_args,
        **kwargs
    )


def host_run(*args, **kwargs):
    kwargs = host_args(*args, **kwargs)
    return subprocess.run(**kwargs)


def host_run_interactive(cmd, *args, host="localhost", ssh_user=None, **kwargs):
    if _is_localhost(host):
        return local_run_interactive(cmd, *args, **kwargs)
    return ssh_run_interactive(host, cmd, *args, ssh_user=ssh_user, **kwargs)
