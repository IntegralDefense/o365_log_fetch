
from configparser import (ConfigParser, ParsingError, DuplicateSectionError,
                          NoSectionError, MissingSectionHeaderError,
                          DuplicateOptionError, Error as ConfigError)
from unittest.mock import MagicMock
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
                    "[SECION2]\n"
                    "option3 = howdy\n"
                    "option3 = neighbor\n")
        with self.assertRaises(DuplicateOptionError):
            ParserWrapper(bad_file, test=True)
