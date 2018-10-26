from datetime import datetime


class O365Token:
    """
    https://docs.microsoft.com/en-us/office/office-365-management-api
    /office-365-management-activity-api-reference

    Format of token:
    {
        "accessToken": "LFunBvIzcwxIk9nwoRXtuXaetsR3qnXy59L3O_n10F-h",
        "expiresOn": "2018-07-30 15:01:51.226457",
        "resource": "https://manage.office.com",
        "tokenType": "Bearer",
        "expiresIn": 3599
    }
    """

    def __init__(self, token_info):
        for key, value in token_info.items():
            setattr(self, key, value)
        self.expiresOn = datetime.strptime(self.expiresOn, "%Y-%m-%d %H:%M:%S.%f")

    def return_authorization_string(self):
        """
        Returns formatted HTTP Auth string.

        Returns
        ----------
        Authorization string:
            Ex: "Bearer LFunBvIzcwxIk9nwoRXtuXaetsR3qnXy59L3O_n10F-h"
        """

        return "{0} {1}".format(self.tokenType, self.accessToken)


def validate_token(func):
    """
    Decorator which checks to see if current token has expired.
    If token has expired, it renews the token before performing
    the requested action against the O365 Activity API.

    """

    def wrapper(*args, **kwargs):
        # args[0] should be O365ManagementApi (self) because this function is
        # called from the O365ManagementApi class.
        try:
            if args[0].token.expiresOn < datetime.now():
                args[0].token = args[0].get_token()
            do_func = func(*args, **kwargs)
            return do_func
        except AttributeError as a:
            raise AttributeError("{0}: Existing token not valid or empty".format(a))

    return wrapper
