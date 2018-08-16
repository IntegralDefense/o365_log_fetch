from datetime import datetime
import unittest

from o365_api.token import O365Token


class TestTokens(unittest.TestCase):

    def setUp(self):
        token_dict = {
            "accessToken": "LFunBvIzcwxIk9nwoRXtuXaetsR3qnXy59L3O_n10F-h",
            "expiresOn": "2018-07-30 15:01:51.226457",
            "resource": "https://manage.office.com",
            "tokenType": "Bearer",
            "expiresIn": 3599
        }
        self.token = O365Token(token_dict)

    def test_return_authorization_string(self):
        expected = "Bearer LFunBvIzcwxIk9nwoRXtuXaetsR3qnXy59L3O_n10F-h"
        self.assertEqual(expected, self.token.return_authorization_string())

    def test_token_expires_on(self):
        expected = datetime(2018, 7, 30, 15, 1, 51, 226457)
        self.assertEqual(expected, self.token.expiresOn)

    # TODO - Need unit tests for validate_token decorator
