# -*- coding: utf-8 -*-
# pylint: disable=logging-fstring-interpolation
# SPDX-License-Identifier: MIT

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


def get_config():
    app_paths = AppDataPaths(MODULE)
    config_path = Path(app_paths.get_config_path(name='config', ext='.ini'))
    if app_paths.require_setup or not config_path.exists():
        config = make_config(app_paths=app_paths, config_path=config_path)
    else:
        logger.debug(f'Found config file at {config_path}')
        config = ConfigParser()
        config.read(config_path)
    return config


def make_config(app_paths: AppDataPaths, config_path: Path) -> ConfigParser:
    logger.debug(f'Creating config file at {config_path}')
    app_paths.setup()
    config = ConfigParser()
    config['DEFAULT'] = {
        'user': 'root',
        'password': 'easybot',
        'dashboard_port': '29999',
        'ssh_port': '22',
        'urtz': 'Europe/Copenhagen',
        'localtz': datetime.datetime.now().astimezone().tzname()
    }
    done = False
    while not done:
        name = Prompt.ask('What is the name or designation of this robot?')
        config[name] = {}
        config[name]['address'] = Prompt.ask(
            'What is the IP address of the robot?')
        config[name]['user'] = Prompt.ask(
            'What is the username on the robot?', default=config.get(section=name, option='user'))
        config[name]['password'] = Prompt.ask(f'What is the password for {config.get(section=name, option="user")} on the robot?', default=config.get(
            section=name, option='password'), password=True)
        done = Confirm.ask('Have you entered all the robots?',
                           default=True, show_default=True, show_choices=True)
    with open(config_path, mode='w', encoding='utf-8') as config_file:
        config.write(config_file)
    return config


def set_robot_time(robot: str, config: ConfigParser) -> bool:
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
        _, stout, sterr = ssh_client.exec_command(
            f'date --iso-8601=ns;date --set="{arrow.get(tzinfo=localtz).to(urtz).isoformat()}" --iso-8601=ns')
    except SSHException as error:
        logger.error(f'Error setting time on {robot} ({robot_addr}): {error}')
        ssh_client.close()
        return False

    out = stout.read()
    err = sterr.read()
    if err:
        logger.error(
            f'Error setting time on {robot} ({robot_addr}): {err.decode()}')
        ssh_client.close()
        return False
    if len(out.split()) != 2:
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
    logger.info(f'Adding message to {robot} log: {message!r}')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((
            config.get(section=robot, option='address'),
            config.getint(section=robot, option='dashboard_port'),
        ))
        sock.sendall(f'addToLog {message}'.encode())
        resp = sock.recv(21)
    if resp != b'Added log message':
        logger.warning(f'Unexpected response from {robot}: {resp.decode()}')
    else:
        logger.debug(f'Successfully added message to {robot} log')


if __name__ == '__main__':
    config = get_config()
    for robot in config.sections():
        success = set_robot_time(robot=robot, config=config)
