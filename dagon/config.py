from configparser import ConfigParser
from collections import defaultdict
from typing import DefaultDict, Dict, Optional, Union, overload

"""
Configuration functions
"""


ConfigSection = Dict[str, str]
ConfigData = DefaultDict[str, ConfigSection]


@overload
def read_config(file_config: str = "dagon.ini", section: None = None) -> ConfigData:
    ...


@overload
def read_config(file_config: str = "dagon.ini", section: str = ...) -> Optional[ConfigSection]:
    ...


def read_config(file_config: str = "dagon.ini", section: Optional[str] = None) -> Union[ConfigData, ConfigSection, None]:
    """
    Reads the configuration file specified

    :param file_config: path to the configuration file
    :type file_config: str

    :param section: section of the file to read
    :type section: str

    :return: dictionary with the configuration
    :rtype: dict(str, dict)
    """
    config = ConfigParser()
    config.read(file_config)
    if section is not None:
        try:
            return dict(config.items(section))
        except:
            return None
    else:
        dictionary = defaultdict(dict)
        for section in config.sections():
            dictionary[section] = {}
            for option in config.options(section):
                dictionary[section][option] = config.get(section, option, raw=True)
        return dictionary
