
from configparser import (DuplicateSectionError, MissingSectionHeaderError,
                          DuplicateOptionError, Error as ConfigError)
from unittest.mock import MagicMoc
from io import StringIO
import unittest

from o365_api.wrappers import FileWrapper, FakeFileWrapper, ParserWrapper


class TestFileWrapper(unittest.TestCase):

    def test_file_wrapper_init(self):
        file_name = 'some_file.txt'
        test_wrapper = FileWrapper(file_name)
        self.assertEqual(file_name, test_wrapper.file_name)


class TestFakeFileWrapper(unittest.TestCase):

    def setUp(self):
        self.text = "Here is some sample text\nthat I put together for you"

    def test_fake_file_wrapper_init(self):
        test_wrapper = FakeFileWrapper(init_text=self.text)
        self.assertTrue(isinstance(test_wrapper.memory_file, StringIO))

    def test_fake_file_wrapper_write(self):
        test_wrapper = FakeFileWrapper()
        test_wrapper.write = MagicMock(name='FakeFileWrapper.write')
        test_wrapper.write(self.text)
        test_wrapper.write.assert_called_with(self.text)

    def test_fake_file_wrapper_open(self):
        test_wrapper = FakeFileWrapper()
        test_wrapper.write(self.text)
        with test_wrapper.open('r') as string_io_file:
            self.assertEqual(self.text, string_io_file.read())


class TestParserWrapper(unittest.TestCase):

    def test_parser_wrapper_init_fail_duplicate_section(self):
        bad_file = ("[SECTION1]\n"
                    "option1 = hello\n"
                    "option2 = world\n"
                    "\n"
                    "[SECION2]\n"
                    "option3 = howdy\n"
                    "option4 = neighbor\n"
                    "\n"
                    "[SECTION1]\n"
                    "option5 = buenos\n"
                    "option6 = noches\n")
        with self.assertRaises(DuplicateSectionError):
            ParserWrapper(bad_file, test=True)

    def test_parser_wrapper_init_fail_missing_section_header(self):
        bad_file = ("option1 = hello\n"
                    "option2 = world\n"
                    "\n"
                    "[SECION2]\n"
                    "option3 = howdy\n"
                    "option3 = neighbor\n"
                    "\n"
                    "[SECTION1]\n"
                    "option5 = buenos\n"
                    "option6 = noches\n")
        with self.assertRaises(MissingSectionHeaderError):
            ParserWrapper(bad_file, test=True)

    def test_parser_wrapper_init_fail_duplicate_option(self):
        bad_file = ("[SECTION1]\n"
                    "option1 = hello\n"
                    "option2 = world\n"
                    "\n"
                    "[SECTION2]\n"
                    "option3 = howdy\n"
                    "option3 = neighbor\n")
        with self.assertRaises(DuplicateOptionError):
            ParserWrapper(bad_file, test=True)

    def test_parser_wrapper_get_option_success(self):
        good_file = ("[SECTION2]\n"
                     "option3 = howdy\n"
                     "option4 = neighbor\n")
        parser = ParserWrapper(good_file, test=True)
        try:
            option = parser.get_option('SECTION2', 'option3')
            self.assertEqual('howdy', option)
        except Exception as e:
            self.fail("Encountered unexpected exception: {}".format(e))

    def test_parser_wrapper_get_option_fail_option_doesnt_exist(self):
        good_file = ("[SECTION2]\n"
                     "option3 = howdy\n"
                     "option4 = neighbor\n")
        parser = ParserWrapper(good_file, test=True)
        self.assertRaisesRegex(
            ConfigError,
            ("Error while getting option from config file: No option 'option7' "
             "in section: 'SECTION2'."),
            parser.get_option,
            'SECTION2',
            'option7',
        )

    def test_parser_wrapper_get_option_fail_section_doesnt_exist(self):
        good_file = ("[SECTION2]\n"
                     "option3 = howdy\n"
                     "option4 = neighbor\n")
        parser = ParserWrapper(good_file, test=True)
        self.assertRaisesRegex(
            ConfigError,
            ("Error while getting option from config file: "
             "No section: 'SECTION9'."),
            parser.get_option,
            'SECTION9',
            'option3',
        )

    def test_parser_wrapper_get_all_options_success(self):
        good_file = ("[SECTION1]\n"
                     "option1 = hello\n"
                     "option2 = world\n"
                     "option3 = how\n"
                     "option4 = are\n"
                     "option5 = you\n"
                     "option6 = today?\n")
        parser = ParserWrapper(good_file, test=True)
        expected = ['hello', 'world', 'how', 'are', 'you', 'today?']
        options = parser.get_all_option_values_in_section('SECTION1')
        self.assertEqual(expected, options)

    def test_parser_wrapper_get_all_options_fail_section_doesnt_exist(self):
        good_file = ("[SECTION1]\n"
                     "option1 = hello\n"
                     "option2 = world\n"
                     "option3 = how\n"
                     "option4 = are\n"
                     "option5 = you\n"
                     "option6 = today?\n")
        parser = ParserWrapper(good_file, test=True)
        self.assertRaisesRegex(
            ConfigError,
            ("Error while getting all option values from config "
             "file: 'NOTVALID'"),
            parser.get_all_option_values_in_section,
            'NOTVALID',
        )


