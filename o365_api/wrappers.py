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
        # Sets buffer position back to zero... so it can be read
        self.memory_file.seek(0)

    def open(self, fake_switch=None):
        return self.memory_file


class ParserWrapper:

    def __init__(self, config_info, test=False):
        self.config_info = config_info
        self.config_parser = ConfigParser()
        self.parse_config(test=test)

    def parse_config(self, test=None):

        if test:
            self.config_parser.read_string(
                self.config_info, source="Unit_Test_String")
        else:
            self.config_parser.read(self.config_info)

    def get_option(self, section, option):

        try:
            return self.config_parser.get(section, option)

        except (ConfigError, KeyError) as e:
            raise ConfigError("Error returning section '{}' option '{}' "
                              "from O365ManagementAPI config file."
                              "".format(section, option, e))

    def get_all_option_values_in_section(self, section):

        try:
            return [values for values in self.config_parser[section].values()]

        except (NoSectionError, KeyError):
            raise KeyError("Section header '{}' is missing from config file."
                           "".format(section, self.config_info))
        except DuplicateSectionError:
            raise DuplicateSectionError("Section header '{}' is duplicated in "
                                        "config file."
                                        "".format(section, self.config_info))
