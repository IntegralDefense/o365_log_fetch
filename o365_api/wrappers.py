from configparser import (ConfigParser, ParsingError, DuplicateSectionError,
                          NoSectionError, Error as ConfigError)
from io import StringIO


class FileWrapper:

    def __init__(self, file_):
        self.file_name = file_

    def open(self, switch='r'):
        return open(self.file_name, switch)


class FakeFileWrapper:

    def __init__(self, init_text=None):
        self.memory_file = StringIO(init_text)

    def write(self, text):
        self.memory_file.write(text)

    def open(self, fake_switch=None):
        return self.memory_file


class ParserWrapper:

    def __init__(self, config_path):
        self.config_path = config_path
        self.config_parser = ConfigParser()
        self.parse_config()

    def parse_config(self):

        try:
            if not self.config_parser.read(self.config_path):
                raise ParsingError("Config file is 'empty or undefined'")

        except ConfigError as e:
            raise ParsingError(
                'Unable to parse config file for '
                'O365ManagementApi: {}'.format(e))

    def get_option(self, section, option):

        try:
            return self.config_parser.get(section, option)

        except (ConfigError, KeyError) as e:
            raise ConfigError("Error returning section '{}' option '{}' "
                              "from O365ManagementAPI config file: {}"
                              "".format(section, option, e))

    def get_all_option_values_in_section(self, section):

        try:
            return [values for values in self.config_parser[section].values()]

        except (NoSectionError, KeyError):
            raise KeyError("Section header '{}' is missing from config file "
                           "'{}'".format(section, self.config_path))
        except DuplicateSectionError:
            raise DuplicateSectionError("Section header '{}' is duplicated in "
                                        "config file '{}'"
                                        "".format(section, self.config_path))
