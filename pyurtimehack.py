# -*- coding: utf-8 -*-
# pylint: disable=logging-fstring-interpolation
# SPDX-License-Identifier: MIT

"""
Hacky script to SSH into a Universal Robot,
 set its time from the local host time,
 and add a log to the UR message log.
"""

import datetime
import logging
import socket
from configparser import ConfigParser
from pathlib import Path

import arrow
from appdata import AppDataPaths
from paramiko import (AuthenticationException, AutoAddPolicy,
                      BadHostKeyException, SSHClient, SSHException)
from rich.logging import RichHandler
from rich.prompt import Confirm, Prompt

MODULE = 'pyURtimehack'

FORMAT = "%(message)s"
logging.basicConfig(
    level="DEBUG",
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger(MODULE)
logging.getLogger('paramiko').setLevel(logging.WARNING)


def get_config() -> ConfigParser:
    """
    Get the program config, or make a new one.

    Returns:
        ConfigParser: the complete program config
    """
    app_paths = AppDataPaths(MODULE)
    config_path = Path(app_paths.get_config_path(name='config', ext='.ini'))
    if app_paths.require_setup or not config_path.exists():
        # no config yet, make a new one
        config = make_config(app_paths=app_paths, config_path=config_path)
    else:
        logger.debug(f'Found config file at {config_path}')
        config = ConfigParser()
        config.read(config_path)
    # generate the string for the local tz
    config['DEFAULT']['localtz'] = datetime.datetime.now().astimezone().tzname()
    return config


def make_config(app_paths: AppDataPaths, config_path: Path) -> ConfigParser:
    """
    Make a new program config from scratch.

    Args:
        app_paths (AppDataPaths): The appdata object for this program
        config_path (Path): The path to the config file

    Returns:
        ConfigParser: the newly-complete config
    """
    logger.debug(f'Creating config file at {config_path}')
    app_paths.setup()
    config = ConfigParser()
    config['DEFAULT'] = {
        'user': 'root',             # default UR username
        'password': 'easybot',      # default UR password
        'dashboard_port': '29999',  # dashboard server port
        'ssh_port': '22',           # default SSH port
        # UR is from Denmark, of course the local time is in Denmark tz...
        'urtz': 'Europe/Copenhagen',
    }
    done = False
    while not done:
        # ask the user for all the robots to work with
        name = Prompt.ask('What is the name or designation of this robot?')
        config[name] = {}
        address = config[name]['address'] = Prompt.ask(
            prompt=f'What is the IP address of the {name} robot?')
        user = config[name]['user'] = Prompt.ask(
            prompt=f'What is the username on the {name} robot?',
            default=config.get(section=name, option='user')
        )
        password = config[name]['password'] = Prompt.ask(
            prompt=f'What is the password for {user} on the {name} robot?',
            default=config.get(section=name, option='password'),
            password=True
        )
        done = Confirm.ask(
            prompt=f'Added {name} robot = {user}:{password}@{address}\n'
            'Have you entered all the robots?',
            default=True,
            show_default=True,
            show_choices=True
        )
    with open(config_path, mode='w', encoding='utf-8') as config_file:
        config.write(config_file)
    return config


def set_robot_time(robot: str, config: ConfigParser) -> bool:
    """
    Set the robot time over SSH.

    This method swallows exceptions in favor of writing them out to log;
      my assumption is that if we cannot set the time after an initial setup,
      when an engineer is expected to be watching logs for issues to resolve,
      then the plant maintenance staff *definitely* knows the robot(s) are not
      talking to the network and it is better just to move on with life.

    Args:
        robot (str): Name of the robot in the config file
        config (ConfigParser): Config object

    Returns:
        bool: success status of the time set
    """
    ssh_client = SSHClient()
    ssh_client.set_missing_host_key_policy(AutoAddPolicy())
    ssh_client.load_system_host_keys()
    try:
        ssh_client.connect(
            hostname=config.get(section=robot, option='address'),
            port=config.getint(section=robot, option='ssh_port'),
            username=config.get(section=robot, option='user'),
            password=config.get(section=robot, option='password'),
        )
    except (BadHostKeyException, AuthenticationException, SSHException, socket.error) as error:
        logger.error(f'Error connecting to {robot}: {error}')
        ssh_client.close()
        return False

    localtz = config.get(section=robot, option='localtz')
    urtz = config.get(section=robot, option='urtz')
    robot_addr = ':'.join(
        map(str, ssh_client.get_transport().sock.getpeername()))
    local_addr = ssh_client.get_transport().sock.getsockname()[0]
    logger.info(
        f'Setting time on {robot} ({robot_addr})')
    try:
        # ask for the current time first, then set the time correctly
        _, stout, sterr = ssh_client.exec_command(
            'date --iso-8601=ns;'
            f'date --set="{arrow.get(tzinfo=localtz).to(urtz).isoformat()}" --iso-8601=ns')
    except SSHException as error:
        logger.error(f'Error setting time on {robot} ({robot_addr}): {error}')
        ssh_client.close()
        return False

    out = stout.read()
    err = sterr.read()
    if err:
        # not expecting content on stderr, so we should log it
        logger.error(
            f'Error setting time on {robot} ({robot_addr}): {err.decode()}')
        ssh_client.close()
        return False
    if len(out.split()) != 2:
        # am expecting two entries in the stdout; one each for the new and old times
        logger.error(
            f'Error setting time on {robot} ({robot_addr}): only got back "{out.decode()}"')
        ssh_client.close()
        return False
    old, new = out.split()
    old = arrow.get(old.decode())
    new = arrow.get(new.decode())
    logger.info(
        f'Successfully set time on {robot} ({robot_addr}): {old} -> {new} (difference {new-old})')
    ssh_client.close()

    message = f'External time set by {local_addr}: {old} -> {new}'
    make_robot_log(robot=robot, config=config, message=message)
    return True


def make_robot_log(robot: str, config: ConfigParser, message: str):
    """
    Add a message to the robot log using the UR dashboard.

    Args:
        robot (str): Name of the robot in the config file
        config (ConfigParser): Config object
        message (str): message to write to the robot log
    """
    logger.info(f'Adding message to {robot} log: {message!r}')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        sock.connect((
            config.get(section=robot, option='address'),
            config.getint(section=robot, option='dashboard_port'),
        ))
        greeting = sock.recv(45).strip()
        logger.debug(f'Connected to {robot}: {greeting.decode()}')
        sock.sendall(f'addToLog {message}\n'.encode())
        resp = sock.recv(21).strip()
    if resp != b'Added log message':
        logger.warning(f'Unexpected response from {robot}: {resp!r}')
    else:
        logger.debug(f'Successfully added message to {robot} log')


def main():
    """Main program logic"""
    config = get_config()
    for robot in config.sections():
        _ = set_robot_time(robot=robot, config=config)


if __name__ == '__main__':
    main()
