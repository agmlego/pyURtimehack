# -*- coding: utf-8 -*-
# pylint: disable=logging-fstring-interpolation

from pathlib import Path

from appdata import AppDataPaths

app_paths = AppDataPaths('pyURtimehack')
def_config_path = Path(app_paths.get_config_path(name='config',ext='.ini'))
