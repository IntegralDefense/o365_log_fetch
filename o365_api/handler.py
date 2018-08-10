from datetime import datetime
import json
import logging
import os
import time

import adal
import requests

from o365_api.wrappers import FileWrapper
from o365_api.token import O365Token, validate_token

"""
http://adal-python.readthedocs.io/en/latest/

https://github.com/AzureAD/azure-activedirectory-library-for-python/
wiki/ADAL-basics

https://github.com/AzureAD/azure-activedirectory-library-for-python/
wiki/Acquire-tokens

https://github.com/AzureAD/azure-activedirectory-library-for-python/
blob/dev/sample/certificate_credentials_sample.py#L59-L68
"""


# Decorators for O365 API communication


def validate_subscription(func):
    """
    Checks to make sure subscription is running.  If not, start it up.

    A subscription is required in order to pull logs from a specific
    content type. If you do not have a subscription running, you will
    not be able to pull the logs down and those logs are not stored to
    be pulled down.

    https://docs.microsoft.com/en-us/office/office-365-management-api/
    office-365-management-activity-api-reference#start-a-subscription

    https://docs.microsoft.com/en-us/office/office-365-management-api/
    office-365-management-activity-api-reference#list-current-subscriptions
    """

    def wrapper(*args, **kwargs):
        if not args[0].check_subscription(kwargs['content_type']):
            raise ValueError("Subscription for {} is not enabled. Please "
                             "enable in your Azure tenant"
                             "".format(kwargs['content_type']))
        else:
            do_func = func(*args, **kwargs)
        return do_func
    return wrapper


# Main classes


class O365ManagementApi:
    """
    Class to interface with the Office 365 Management Activity API

    https://manage.office.com/api/v1.0/{tenant_id}/activity/feed/{operation}

    Overview of how we acquire logs:

    1. Look to see if the content type (ex: Audit.Exchange) has an
        active subscription. If not, we attempt to start the
        subscription.
    2. Ask O365 Management API for a list of available log locations.
        The locations are endpoints you can query to pull down a set
        of logs.
    3. Iterate through that list of log locations and pull down the
        logs at each location i.e. 'endpoint. The group of log events
        at each endpoint is known as a 'blob'. It consists of metadata
        and then an object with multiple activity logs listed.
    4. Add the blob metadata to each event in the blob and log it.
        Example of metadata would be the URL that we pulled the
        blob from or the content type that makes up the blob.

    We use the 'validate_token' decorator to ensure each call has a
    valid token. If not, then we acquire a new access token. This
    should only be a factor when you are pulling large quantities
    of data instead of in increments.

    We risk running into an issue if we do not include the tenantID
    (uuid) in the API calls as 'PublisherIdentifier'. Microsoft's API
    rate limits per tenantID. As of 2018-08-10, that limit is 60k
    requests per minute. If we do not specify the
    'PublisherIdentifier', we will be rate-limited based on the
    globally shared tenant uuid.

    From

    https://docs.microsoft.com/en-us/office/office-365-management
    -api/office-365-management-activity-api-reference#activity-
    api-operations

    All API operations require an Authorization HTTP header with an
    access token obtained from Azure AD. The tenant ID in the access
    token must match the tenant ID in the root URL of the API and the
    access token must contain the ActivityFeed.Read claim (this
    corresponds to the permission [Read activity data for an
    organization] that you configured for you application in
    Azure AD).

    Attributes
    ----------
    config: o365_api.wrappers.ConfigParserWrapper
        Wrapper to interface with ConfigParser. This will be used to
        pull configuration as needed from the config file.

    log_location: str
        Directory where the O365 Acitivity API logs will be stored.

    debug_location: str
        Directory where the logs generated from this program will be
        stored.

    time_location: str
        Directory where the file is located to read/write last program
        run. This is used to determine how far back the current run
        of the program needs to pull logs when querying the Microsoft
        API.

    authority_url: str
        The URL to send signed JWT token (URL is an endpoint on Azure
        Active Directory) in order to get an access token to actually
        query the O365 Management Activity API.

    key: str
        Private key used to sign the JWT token used against Azure
        Active Directory.  The matching public key must be configured
        in the Application Registration.

    content_types: list
        List of content types that we are interested in getting logs
        from. Ex: Audit.Exchange, Audit.Sharepoint, etc.

    end_time: int
        Epoch of the last timestamp queried during this run of the
        program. Will be saved to file after the run for use during
        the next run of the program.

    token: o365_api.token.O365Token
        Object to hold access token information and can be used to
        generate the HTTP Authorization string on calls to the
        O365 Management Activity API.

    run_id: str
        UUID used for logging purposes. Helps with debugging
        the program.

    """

    def __init__(self, config_parser, start_time=None,
                 end_time=None, run_id=None):
        """
        Initialize an instance of the class

        Notice that the settings are pulled from a ini-style config
        file.
        """
        self.config = config_parser
        self.log_location = self.config.get_option('LOGGING', 'baseLogLocation')
        self.debug_location = self.config.get_option(
            'LOGGING', 'debugLogLocation')
        self.time_location = self.config.get_option(
            'LOGGING', 'timeKeeperLocation')
        self.authority_url = ("{0}/{1}".format(
            self.config.get_option('API_SETTINGS', 'authorityHostUrl'),
            self.config.get_option('API_SETTINGS', 'tenant')
        ))
        self.key = self.get_private_key(
            self.config.get_option('API_SETTINGS', 'privateKeyFile')
        )
        self.content_types = self.config.get_all_option_values_in_section(
            'ContentTypes')
        self.start_time = (start_time
                           or self._get_last_log_time()
                           or (int(time.time()) - 600)
                           )
        self.end_time = end_time or int(time.time())
        self.token = self.get_token()
        self.run_id = run_id

    def get_token(self):
        """
        Get a new access token.

        Uses the ADAL library from Microsoft to authenticate
        via Certificate-based Client Credentials.

        http://adal-python.readthedocs.io/en/latest/
        https://github.com/AzureAD/azure-activedirectory-library-for-python/
            wiki/ADAL-basics
        https://github.com/AzureAD/azure-activedirectory-library-for-python/
            wiki/Acquire-tokens
        https://github.com/AzureAD/azure-activedirectory-library-for-python/
            blob/dev/sample/certificate_credentials_sample.py#L59-L68



        Returns
        ----------
        O365Token: obj
            O365Token object built from the context ADAL library response
        """

        context = adal.AuthenticationContext(
            self.authority_url,
            verify_ssl=False
        )

        token = context.acquire_token_with_client_certificate(
            self.config.get_option('API_SETTINGS', 'resource'),
            self.config.get_option('API_SETTINGS', 'clientID'),
            self.key,
            self.config.get_option('API_SETTINGS', 'thumbprint')
        )

        return O365Token(token)

    @staticmethod
    def get_private_key(file_name, file_wrapper=None):
        """
        Reads the private key file and returns as a string

        Parameters
        ----------
        file_name: str
            File location.  Ex:  "/o365/etc/private_key_file.pem"
        file_wrapper: FileWrapper
            FileWrapper or FakeFileWrapper - makes unit testing easier

        Returns
        ----------
        private_pem: str
            Returns a string representation of the private key
        """
        file_wrap = file_wrapper or FileWrapper(file_name)
        with file_wrap.open() as pem_file:
            private_pem = pem_file.read()
            return private_pem

    @validate_token
    def check_subscription(self, content_type):
        uri = "{0}/subscriptions/list".format(
            self.config.get_option('API_SETTINGS', 'activityApiRoot'))
        headers = {'Authorization': self.token.return_authorization_string()}
        parameters = {
            'PublisherIdentifier': self.config.get_option(
                'API_SETTINGS', 'tenantId')
        }
        subscription_enabled = False
        count = 0
        while not subscription_enabled:
            r = requests.get(uri, params=parameters, headers=headers)
            try:
                enabled_content_types = [
                    subscription['contentType'] for subscription in r.json()
                    if subscription['status'] == 'enabled']
            except TypeError:
                raise TypeError(
                    'Unexpected Message when checking subscription: {}'.format(
                        r.text)
                )
            if content_type not in enabled_content_types:
                print('No subscription for {}'.format(content_type))
                try:
                    self.start_subscription(content_type)
                except (ValueError, KeyError):
                    print("Error starting subscription")
                    return False
                count += 1
                if count == 3:
                    return False
            else:
                # print('Found subscription {}'.format(content_type))
                return True

    @validate_token
    def start_subscription(self, content_type):
        print('starting subscription for {}'.format(content_type))
        """
        Note that PublisherIdentifier is the GUID of the app writer,
        not the app user.

        https://docs.microsoft.com/en-us/office/office-365-management
        -api/office-365-management-activity-api-reference#start-a-
        subscription

        :param content_type:
        :return:
        """
        uri = "{0}/subscriptions/start".format(
            self.config.get_option('API_SETTINGS', 'activityApiRoot')
        )
        headers = {
            'Authorization': self.token.return_authorization_string(),
            'Content-Type': 'application/json'
        }
        parameters = {
            'contentType': content_type,
            'PublisherIdentifier': self.config.get_option(
                'API_SETTINGS', 'tenantId')
        }
        body = '{}'
        r = requests.post(uri, data=body, params=parameters, headers=headers)
        try:
            if r.json()['status'] != 'enabled':
                raise ValueError('Subscription did not enable properly. {}'
                                 ''.format(json.dumps(r.json())))
            else:
                pass
        except KeyError:
            raise KeyError('Status not available in \'start subscription\' '
                           'response: {}'.format(json.dumps(r.json())))

    @validate_token
    @validate_subscription
    def retrieve_logs(self, content_type=None):
        """
        Gets the logs from O365 Management Activity API.

        You can specify the specific content type You can add start/end
        times as well if using a cron job and require logs at a smaller
        interval than the default of 24 hours. Microsoft has
        recommendations on specifying time ranges:

        https://docs.microsoft.com/en-us/office/office-365-management
        -api/office-365-management-activity-api-reference#list-
        available-content

            - Returns content as it became 'available' in the
                specified range
            - Time range is inclusive for startTime:
                (startTime <= contentCreated)
            - Time range is exclusive for endTime:
                (contentCreated < endTime)
            - Can have the following formats for times in UTC:
                YYYY-MM-DD
                YYYY-MM-DDTHH:MM
                YYYY-MM-DDTHH:MM:SS
            - Both startTime and endTime must be specified (or both
                omitted) and they must be no more than 24 hours apart,
                with the start time no more than 7 days in the past.
                By default, if startTime and endTime are omitted,
                then the content available in the last 24 hours is
                returned.
            - The recommendation (to avoid partials) is to NOT perform
                a request for more than 24 hours between start and end.

        Parameters
        ----------
        content_type: str
            The content type to pull down from O365 Management Activity
            API. If this parameter is 'None', then we will pull all
            content types that are listed in the config file.
        """

        uri = "{0}/subscriptions/content".format(
            self.config.get_option('API_SETTINGS', 'activityApiRoot'))
        headers = {
            'Authorization': self.token.return_authorization_string()
        }
        parameters = {
            'PublisherIdentifier': self.config.get_option(
                'API_SETTINGS', 'tenantId'),
            'contentType': content_type,
            'startTime': self._start_epoch_to_readable_str('%Y-%m-%dT%H:%M:%S'),
            'endTime': self._end_epoch_to_readable_str('%Y-%m-%dT%H:%M:%S')
        }
        print("Begin run. Range: {} to {}".format(
                  parameters['startTime'], parameters['endTime']))
        r = requests.get(uri, params=parameters, headers=headers)

        # Log blobs are groups of events that can be pulled from the
        # Api. Log blob 'locations' are the endpoints in which you
        # must query to pull down those lob blobs. When you list
        # content, you actually list the blob locations.  You must
        # then go pull down the contents of those log blob locations
        blob_locations = [blob_info for blob_info in r.json()]
        for blob_content in blob_locations:
            print(blob_content)
            try:
                self._get_content(blob_content)
            except Exception as e:
                self._log_writer(logging.exception, "{}".format(e))

            # Format each individual event to contain the metadata
            # and then write to file.
            # TODO - handle error handling for write function
            for event in blob_content['contentData']:
                count = 0
                while True and (count < 3):
                    try:
                        event['contentType'] = blob_content['contentType']
                        event['contentUri'] = blob_content['contentUri']
                        event['contentId'] = blob_content['contentId']
                    except TypeError:
                        # print("TYPE ERROR")
                        if event == 'error' and count < 2:
                            # TODO - Probably too many requests. LOG IT
                            print(json.dumps(blob_content))
                            print("Sleeping count was {}".format(str(count)))
                            count += 1
                            time.sleep(15)
                            continue
                        elif count == 2:
                            #TODO - Log that there was an issue with retries
                            print("Issue with retries...")
                            break
                        else:
                            break
                    break
                local_log_file = os.path.join(
                    self.log_location, "{}.log".format(event['contentType']))
                with open(local_log_file, 'a+') as write_file:
                    write_file.write("{}\n".format(json.dumps(event)))

    @validate_token
    def _get_content(self, blob_meta):
        try:
            uri = blob_meta['contentUri']
            headers = {
                'Authorization': self.token.return_authorization_string()
            }
            parameters = {
                'PublisherIdentifier': self.config.get_option(
                    'API_SETTINGS', 'tenantId')
            }
            print(uri)
            r = requests.get(uri, params=parameters, headers=headers)
            blob_meta['contentData'] = r.json()
        except TypeError:
            raise TypeError('blob_meta is not what you think...')

    def _get_last_log_time(self):
        file_wrapper = FileWrapper(os.path.join(self.time_location, 'time.log'))
        with file_wrapper.open() as time_file:
            epoch_time = time_file.readline()
        try:
            return int(epoch_time)
        except ValueError:
            return None

    def _save_last_log_time(self):
        """
        Saves the end-time defined for the current run of the program.


        :return:
        """
        file_wrapper = FileWrapper(os.path.join(self.time_location, 'time.log'))
        with file_wrapper.open('w') as time_file:
            time_file.write(str(self.end_time))

    def _start_epoch_to_readable_str(self, format_):
        return datetime.fromtimestamp(int(self.start_time)).strftime(format_)

    def _end_epoch_to_readable_str(self, format_):
        return datetime.fromtimestamp(int(self.end_time)).strftime(format_)

    def _log_writer(self, log_type, message):
        """
        Prepends 'JobId' to the log being written.

        Handy for tracking through the debug logs

        Parameters
        ----------
        log_type: log object
            Ex:  logging.exception, logging.info, etc.
        message: str
            Message to be written to the log
        """
        log_type("JobId={0} {1}".format(self.run_id, message))
