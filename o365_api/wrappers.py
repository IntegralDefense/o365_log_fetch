from configparser import ConfigParser, Error as ConfigError
from io import StringIO


class FileWrapper:

    """
    Used to wrap files.

    Use this class instead of the normal file
    handlers and you can replace it with 'FakeFileWrapper' for
    unit testing with StringIO instead of using the filesystem
    """

    def __init__(self, file_):
        """
        Initialize the file wrapper

        Parameters
        ----------
        file_: str
            File name
        """

        self.file_name = file_

    def open(self, switch="r"):
        """
        Return a file handler.

        Parameters
        ----------
        switch: str
            The switches used with a typical file object.
            Ex: r, w, etc.

        Returns
        ----------
        file handler
        """

        return open(self.file_name, switch)


class FakeFileWrapper:
    """
        Used to wrap StringIO

        This can be used in leiu of 'FileWrapper' during unit testing
        to avoid using the filesystem.
    """

    def __init__(self, init_text=None):
        """
        Initialization of FakeFileWrapper.

        If there is text to preload, we also use .seek(0) to move the
        buffer back to the initial location. This aids in reading
        the StringIO object later.

        Parameters
        ----------
        init_text: str
            The text you wish to preload into the StringIO object
        """

        self.memory_file = StringIO(init_text)
        if init_text:
            self.memory_file.seek(0)

    def write(self, text):
        """
        Add text to the StringIO object.

        We add the text and then use 'seek(0)' to move the
        buffer back to the initial location. This aids in reading
        the StringIO object later.

        :param text:
        :return:
        """
        self.memory_file.write(text)
        self.memory_file.seek(0)

    def open(self, fake_switch=None):
        """
        Returns the StringIO object instead of an actual file handler.

        This is useful in unit tests.

        Parameters
        ----------
        fake_switch: str
            This is not used.  It's a placeholder becuase there would
            a string here if the normal file wrapper is used. We add
            the placeholder so that there are no 'unexpected argument'
            issues.

        Returns
        ----------
        StringIO object
        """

        return self.memory_file


class ParserWrapper:
    """
    Used to wrap config parser.

    Helpful when unit testing as you can send a string in ini format
    or an ini-formatted file.

    Handling errors here so that we don't have to do it throughout the
    rest of the program.
    """

    def __init__(self, config_info, test=False):
        """
        If test is True, then config_info will be a string mimicking
        an ini file. If False, we assume it's an actual file name.

        Parameters
        ----------
        config_info: str
            This could be a filename or a string that mimics a file
            in .ini format.
        test: bool
            True - config_info is a string mimicking an ini file. This
            is handy for unit testing
            False - config_info is a file name

        """
        self.config_info = config_info
        self.config_parser = ConfigParser()
        self.parse_config(test=test)

    def parse_config(self, test=None):
        """
        Parse the config file with ConfigParser and store it as an
        attribute for the ParserWrapper object.

        Parameters
        ----------
        test: bool
            True - self.config_info is a string in ini file format
            False - self.config_info is a file name to be read
        """

        if test:
            self.config_parser.read_string(self.config_info, source="Unit_Test_String")
        else:
            self.config_parser.read(self.config_info)

    def get_option(self, section, option):
        """
        Get an option from the config parser object

        Parameters
        ----------
        section: str
            The Section where the required option resides
        option: str
            The option you want the value from

        Returns
        ----------
        The option as a string

        Raises
        ----------
        ConfigError
            Returns if there was any error getting the option.
        """

        try:
            return self.config_parser.get(section, option)

        except (ConfigError, KeyError) as e:
            raise ConfigError(
                "Error while getting option from config file: {}." "".format(e)
            )

    def get_all_option_values_in_section(self, section):
        """
        Returns a list of all the options in a section

        Parameters
        ----------
        section: str
            The section you wish to list the options from.

        Returns
        ----------
        List of option values from the specified section

        Raises
        ----------
        ConfigError
            Raised if there were any issues listing the options.
        """

        try:
            return [values for values in self.config_parser[section].values()]

        except (ConfigError, KeyError) as e:
            raise ConfigError(
                "Error while getting all option values from "
                "config file: {}"
                "".format(e)
            )

