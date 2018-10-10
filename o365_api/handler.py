from urllib.parse import urljoin
from datetime import datetime
import asyncio
import json
import logging
import os
import time

import adal
import aiohttp
# import requests

from o365_api.wrappers import FileWrapper
from o365_api.token import O365Token

"""
http://adal-python.readthedocs.io/en/latest/

https://github.com/AzureAD/azure-activedirectory-library-for-python/
wiki/ADAL-basics

https://github.com/AzureAD/azure-activedirectory-library-for-python/
wiki/Acquire-tokens

https://github.com/AzureAD/azure-activedirectory-library-for-python/
blob/dev/sample/certificate_credentials_sample.py#L59-L68
"""




class O365ManagementApi:
    """
    Class to interface with the Office 365 Management Activity API

    https://manage.office.com/api/v1.0/{tenant_id}/activity/feed/{operation}

    Overview of how we acquire logs (post-authentication):

    1. Look to see if the content type (ex: Audit.Exchange) has an
        active subscription. If not, we attempt to start the
        subscription.
    2. Ask O365 Management API for a list of available log locations.
        The locations are endpoints you can query to pull down a set
        of logs.
    3. Iterate through that list of log locations and pull down the
        logs at each location i.e. 'endpoint'. The group of log events
        at each endpoint is known as a 'blob'.
    4. Add the blob metadata (from the list of available content) to
        each event in the blob and log it. Example of metadata would
        be the URL that we pulled the blob from or the content type
        that makes up the blob.

    We use the 'validate_token' decorator to ensure each call has a
    valid token. If not, then we acquire a new access token. This
    should only be a factor when you are pulling large quantities
    of data instead of in increments as the usual lifetime of the
    Bearer token seems to be one hour.

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
        Active Directory. The matching public key must be configured
        in the Application Registration.

    content_types: list
        List of content types that we are interested in getting logs
        from. Ex: Audit.Exchange, Audit.Sharepoint, etc.

    start_time: int
        Epoch of the earliest time you wish to pull logs from. Pulls
        this time in the following order:  1. From CLI argument,
        2. From the time.log file indicating the last run, 3. ten
        minutes ago.

    end_time: int
        Epoch of the last timestamp queried during this run of the
        program. Will be saved to file after the run for use during
        the next run of the program. 1. From CLI argument, 2. now.

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
        """

        self.config = config_parser
        self.log_location = self._get_logging_setting('baseLogLocation')
        self.debug_location = self._get_logging_setting('debugLogLocation')
        self.time_location = self._get_logging_setting('timeKeeperLocation')
        self.authority_url = urljoin(
            self._get_api_setting('authorityHostUrl'),
            self._get_api_setting('tenant')
        )
        self.key = self.get_private_key()
        self.content_types = self.config.get_all_option_values_in_section(
            'ContentTypes')
        self.pub_id = self._get_api_setting('tenantId')
        self.root_api = self._get_api_setting('activityApiRoot')
        self.start_time = (
            start_time or self._get_last_log_time() or (int(time.time()) - 600)
        )
        self.end_time = end_time or int(time.time())
        # Microsoft recommends no more than 24 hrs when listing available
        # content endpoints.
        self.windows = self._split_time_into_24_hr_chunks()
        self.token = self.get_token()
        self.run_id = run_id
        self.loop = None
        self.session = None
        self.inactive_subscriptions = []
        self.content_locations = {}
        self.events = {}
        self.events_count = {}

    def _split_time_into_24_hr_chunks(self):
        window = int(self.end_time) - int(self.start_time)
        list_ = []
        start = int(self.start_time)
        while window > 86400:
            end = start + 86400
            list_.append({'start': start, 'end': end})
            start = end
            window -= 86400
        list_.append({'start': start, 'end': int(self.end_time)})
        window_count = str(len(list_))
        logging.info(
            'This run will be broken up into {} sections: {}'
            ''.format(window_count, json.dumps(list_))
        )
        return list_

    def _get_api_setting(self, setting):
        return self.config.get_option('API_SETTINGS', setting)

    def _get_logging_setting(self, setting):
        return self.config.get_option('LOGGING', setting)

    def get_token(self):
        """
        Get a new access token.

        Uses the ADAL library from Microsoft to authenticate
        via Certificate-based Client Credentials.

        1. Send signed JWT token to Azure Active Directory.
        2. If JWT token is verified, you will receive an access token
            which can be used to query the O365 Management Activity
            API.

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
            self._get_api_setting('resource'),
            self._get_api_setting('clientID'),
            self.key,
            self._get_api_setting('thumbprint'),
        )

        return O365Token(token)

    def get_private_key(self, file_wrapper=None):
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

        key_file = self._get_api_setting('privateKeyFile')
        file_wrap = file_wrapper or FileWrapper(key_file)
        with file_wrap.open() as pem_file:
            private_pem = pem_file.read()
            return private_pem

    # API CALLS #

    async def run(self, loop):
        self.loop = loop
        async with aiohttp.ClientSession(loop=loop) as session:
            self.session = session
            coroutine_ = self.o365_log_foreman()
            await asyncio.gather(coroutine_, loop=self.loop)

    async def o365_log_foreman(self):
        await self.handle_subscriptions()
        await self.get_logs()

    # ##### SUBSCRIPTIONS - ASYNC methods

    async def handle_subscriptions(self):
        http_args = {
            'url': urljoin(self.root_api, 'subscriptions/list'),
            'headers': {
                'Authorization': self.token.return_authorization_string()
            },
            'params': {'PublisherIdentifier': self.pub_id},
        }

        r_json, _ = await self._api_get(**http_args)
        # Get inactive subscriptions
        inactive_subs = self._get_inactive_subscriptions(r_json)
        # Activate inactive subscriptions
        await self._activate_inactive_subscriptions(inactive_subs)

    async def _activate_inactive_subscriptions(self, inactive_subs_):
        if not inactive_subs_:
            return
        inactive_sub_tasks = self._coroutines_for_subs(inactive_subs_)
        if inactive_sub_tasks:
            await asyncio.gather(*inactive_sub_tasks, loop=self.loop)

    async def _start_subscription(self, content_type):
        api_args = self._start_subscription_args(content_type)
        await self._start_subscription_attempt_loop(**api_args)

    async def _start_subscription_attempt_loop(self, **kwargs):
        remaining_attempts = 3
        while remaining_attempts:
            attempt_num = str(4 - remaining_attempts)
            logging.info('Subscription start attempt {}'.format(attempt_num))
            json_, header_ = await self._api_post(**kwargs)
            if self._sub_start_successful(json_, header_):
                logging.info(
                    'Subscription started successfully for {0}'
                    ''.format(kwargs['params']['contentType'])
                )
                break
            remaining_attempts -= 1
            if not remaining_attempts:
                logging.error(
                    'Subscription for \'{0}\' could not be started after 3 '
                    'attempts. No logs will be gathered for this content '
                    'type.'.format(kwargs['params']['contentType'])
                )
                self.inactive_subscriptions.append(
                    kwargs['params']['contentType']
                )

    async def _api_get(self, content_type='application/json', encoding=None, **kwargs):
        async with self.session.get(ssl=False, **kwargs) as r:
            if r.status != 200:
                logging.error('{}, {}, {}'.format(r.url, r.status, r.reason))
                raise ValueError(
                    'API call returned status that was not 200 - Status: {},'
                    ' Reason: {}, URL: {}, Headers: {}'
                    ''.format(r.status, r.reason, r.url, r.headers)
                )
            json_ = await r.json(content_type=content_type, encoding=encoding)
            headers_ = r.headers
            return json_, headers_

    async def _api_post(self, content_type='application/json', encoding=None, **kwargs):
        async with self.session.post(ssl=False, **kwargs) as r:
            if r.status != 200:
                logging.error('{}, {}, {}'.format(r.url, r.status, r.reason))
                raise ValueError(
                    'API call returned status that was not 200 - Status: {},'
                    ' Reason: {}, URL: {}, Headers: {}'
                    ''.format(r.status, r.reason, r.url, r.headers)
                )
            json_ = await r.json(content_type=content_type, encoding=encoding)
            headers_ = r.headers
            return json_, headers_

    # ##### SUBSCRIPTIONS - Syncronous methods

    def _get_inactive_subscriptions(self, r_json):
        try:
            inactive_subs = self._list_inactive_subs(r_json)
        except (TypeError, KeyError) as e:
            logging.exception(
                'Failure while checking for inactive subscriptions. List '
                'subscription API call response: {}'.format(r_json)
            )
            raise
        else:
            length = len(inactive_subs)
            logging.info(
                'There are {} inactive subscriptions.'.format(length)
            )
            return inactive_subs

    def _coroutines_for_subs(self, inactive_subs):
        coroutines_ = []
        for content_type in self.content_types:
            if content_type in inactive_subs:
                coroutines_.append(self._start_subscription(content_type))
        return coroutines_

    def _start_subscription_args(self, content_type):
        http_args = {
            'url': urljoin(self.root_api, 'subscriptions/start'),
            'headers': {
                'Authorization': self.token.return_authorization_string(),
                'Content-Type': 'application/json',
            },
            'params': {
                'contentType': content_type,
                'PublisherIdentifier': self.pub_id,
            },
            'data': '{}',
        }
        return http_args

    def _sub_start_successful(self, json_, header_):
        try:
            if json_['status'] != 'enabled':
                return False
        except KeyError:
            logging.error(
                "Error when trying to start subsciption. Actual response: {0}"
                "".format(json.dumps(json_))
            )
            return False
        else:
            return True

    def _list_inactive_subs(self, json_):
        inactive_subs = []
        for subscription in json_:
            try:
                if subscription['status'] != 'enabled':
                    inactive_subs.append(subscription['contentType'])
            except TypeError as t:
                raise TypeError(
                    'Unexpected Message when checking subscription:'
                    ' {}'.format(t.message)
                )
            except KeyError:
                raise KeyError(
                    'status or contentType key missing response from '
                    'subscription list API.'
                )
        return inactive_subs

    # ##### Get_logs - Async

    async def get_logs(self):
        coroutines = []
        for type_ in self.content_types:
            if type_ in self.inactive_subscriptions:
                continue
            self.events[type_] = []
            self.events_count[type_] = 0
            for window in self.windows:
                coroutines.append(self._get_logs(type_, win=window))

        await asyncio.gather(*coroutines, loop=self.loop)

    async def _get_logs(self, type_, win=None, endpoint=None):
        await self._get_locations(type_, win=win, endpoint=endpoint)
        location_length = str(len(self.content_locations[type_]))
        logging.info(
            'Log type {} has total of {} locations'
            ''.format(type_, location_length)
        )

        await self._get_contents(type_)
        self._write_events_to_file(type_)

    def _write_events_to_file(self, type_):
        """
        Writes the single event to a log file based on the content
        type of the event.

        Parameters
        ----------
        event: dict
            Dictonary containing the event payload and metadata.
            Will be written to file in JSON format.
        """
        try:
            length = str(len(self.events[type_]))
            logging.info('Writing {} events for {}'.format(length, type_))
            file_name = "{}.log".format(type_)
            file_path = os.path.join(self.log_location, file_name)
            with open(file_path, 'a+') as write_file:
                for event in self.events[type_]:
                    write_file.write("{}\n".format(json.dumps(event)))
        except KeyError as k:
            logging.info('Type {} has no events to write.'.format(type_))

    async def _get_contents(self, type_):
        locations = [loc for loc in self.content_locations[type_]]
        coroutines = [
            self._get_log_content(type_, location) for location in locations
        ]
        await asyncio.gather(*coroutines, loop=self.loop)
        logging.info(
            'Log type {} received {} events in total'
            ''.format(type_, self.events_count[type_])
        )

    async def _get_log_content(self, type_, location):
        http_args = {
            'url': location['contentUri'],
            'headers': {
                'Authorization': self.token.return_authorization_string(),
            },
            'params': {
                'PublisherIdentifier': self.pub_id,
            },
        }
        json_, _ = await self._api_get(content_type=None, **http_args)

        events_length = len(json_)
        self.events_count[type_] += events_length
        logging.debug(
            'There were {} events in a location for {}'
            ''.format(str(events_length), type_)
        )

        for log in json_:
            event = {**log, **location}

            self.events[type_].append(event)

    async def _get_locations(self, type_, win=None, endpoint=None, cnt=0):
        http_args = self._location_args(type_, window=win, endpoint=endpoint)

        if not endpoint:
            self.content_locations[type_] = []

        locations_list, r_headers = await self._api_get(**http_args)

        length = str(len(locations_list))
        logging.debug(
            'Received {} locations on the {} iteration for type {}'
            ''.format(length, str(cnt), type_)
        )

        self.content_locations[type_] += locations_list

        if 'NextPageUri' in r_headers:
            next_endpoint = r_headers['NextPageUri']
            cnt += 1
            await self._get_locations(type_, endpoint=next_endpoint, cnt=cnt)

    def _location_args(self, type_, window=None, endpoint=None):
        if not endpoint:
            http_args = {
                'url': urljoin(self.root_api, 'subscriptions/content'),
                'headers': {
                    'Authorization': self.token.return_authorization_string()
                },
                'params': {
                    'PublisherIdentifier': self.pub_id,
                    'contentType': type_,
                    'startTime': self._start_str(window),
                    'endTime': self._end_str(window)
                }
            }
        else:
            http_args = {
                'url': endpoint,
                'headers': {
                    'Authorization': self.token.return_authorization_string()
                },
            }
        return http_args

    def _get_last_log_time(self):
        """
        Pulls the last 'end-time' of this program. This is handy if the
        system may have missed a cron job run and the time elapsed
        since the last run is greater than ten minutes.

        Returns
        ----------
        epoch_time: int
            Last 'end-time' of this program
        None
            File wasn't found or the contents in the file couldn't be
            converted to an integer.
        """

        try:
            file_wrapper = FileWrapper(
                os.path.join(self.time_location, 'time.log'))
            with file_wrapper.open() as time_file:
                epoch_time = time_file.readline()
                return int(epoch_time)
        except (FileNotFoundError, ValueError):
            return None

    def save_last_log_time(self):
        """
        Saves the end-time defined for the current run of the program.

        Parameters
        ----------
        format_: str
            Format you wish the string output to be in

        Returns
        ----------
        datetime string
            String format of the datetime object.
        """

        file_wrapper = FileWrapper(
            os.path.join(self.time_location, 'time.log')
        )
        with file_wrapper.open('w') as time_file:
            time_file.write(str(self.end_time))

    def _start_str(self, window, format_=None):
        """
        Returns readable string of current program's start_time value.

        Parameters
        ----------
        format_: str
            Format you wish the string output to be in

        Returns
        ----------
        datetime string
            String format of the datetime object.
        """
        start = int(window['start'])
        str_format_ = format_ or '%Y-%m-%dT%H:%M:%S'
        return datetime.fromtimestamp(start).strftime(str_format_)

    def _end_str(self, window, format_=None):
        """
        Returns readable string of current program's end_time value.
        """

        end = int(window['end'])
        str_format_ = format_ or '%Y-%m-%dT%H:%M:%S'
        return datetime.fromtimestamp(end).strftime(str_format_)

    '''
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
    '''
