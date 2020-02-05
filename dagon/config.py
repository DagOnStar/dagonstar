from configparser import SafeConfigParser
from collections import defaultdict

"""
Configuration functions
"""


def read_config(file_config="dagon.ini", section=None):
    """
    Reads the configuration file specified

    :param file_config: path to the configuration file
    :type file_config: str

    :param section: section of the file to read
    :type section: str

    :return: dictionary with the configuration
    :rtype: dict(str, dict)
    """
    config = SafeConfigParser()
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
                # print option
                dictionary[section][option] = config.get(section, option, raw=True)
        return dictionary
