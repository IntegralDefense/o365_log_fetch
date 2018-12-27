# o365_log_fetch
Tool to fetch and log O365 Management Activity API logs in a SIEM-friendly json format.

## Overview

This script utilizes Asyncio due to the large quantity of API calls that must be made. In testing, this increased performance (time based) by ~94% as compared to the old, sequential version.

The Office 365 Management Activity API can be used to pull event logs for Exchange online, Sharepoint, Azure Active Directory, General, and DLP logs. Examples of these logs are administrator actions, event logs, authentications, etc.

https://docs.microsoft.com/en-us/office/office-365-management-api/office-365-management-apis-overview#office-365-management-activity-api

### 1. Authentication

Log into your Azure Active Directory tenant as a global administrator. Go to your app registrations and register a new application as documented here:

https://docs.microsoft.com/en-us/office/office-365-management-api/get-started-with-office-365-management-apis#configure-an-x509-certificate-to-enable-service-to-service-calls

NOTE - Be sure to register as a Wep App/ API since this script was designed to be used with one tenant per deployment.

Be sure to upload the public key of your x.509 certificate into the manifest by first formatting it with the powershell script in the link above for server-to-service calls. You will use the private key with the Python ADAL library to sign JWT assertions.

There is also a requirement that ADAL needs to know the thumbprint of the cert as listed in the app registration. The 'API_SETTINGS' section has an option labeled 'thumbprint' which will be used for the JWT assertion.  Without this thumbprint, the API will not know what key to use in order to verify the signature of the JWT assertion. You can get this thumbprint by going to yoru Azure Active Directory tenant, then App Registrations > Your App > Settings > Keys > Public Keys.

Be sure to note your App ID, as well as your Tenant ID / Directory ID as it is needed in the config file:

  App ID - Found in app registration
  Tenant ID - Listed as 'Directory ID' in 'Azure Active Directory > Properties'

https://docs.microsoft.com/en-us/office/office-365-management-api/get-started-with-office-365-management-apis#request-an-access-token-by-using-client-credentials

If you have any issues, try having another tenant admin grant consent as documented here:

https://docs.microsoft.com/en-us/office/office-365-management-api/get-started-with-office-365-management-apis#get-office-365-tenant-admin-consent

Once the script is able to authenticate to Azure Active Directory using the JWT assertion, Azure Active Directory will return an access token that will allow our script to access the O365 Management Activity API with an 'Authorization' header in the API call.

See Service-to-Service calls using client credentials:  https://msdn.microsoft.com/en-us/library/azure/dn645543.aspx

### 2. Config file setup

Adjust the o365_logs.cfg to match your environment.

Config section notes:

#### API_SETTINGS
The 'ActivityApiRoot' option is automatically generated upon parsing of the file by ConfigParser (inerpolation).
The 'autoStartSubscriptions' option, when set to 'True' will automatically try to start inactive subscriptions for the content types that you set int he 'ContentTypes' section. It can take up to 12 hours for the log blobs to become available after starting a subscription.
 
#### ContentTypes
List the content types you wish to pull logs from. You can find a list of valid content types in the O365 Management Activity API documentation: https://docs.microsoft.com/en-us/office/office-365-management-api/office-365-management-activity-api-reference#working-with-the-office-365-management-activity-api

#### Logging
The locations you wish log to.

  baseLogLocation - The directory you want the events from the O365 Management Activity API logs to be stored. The file names will be automatically generated based on content type.  For example: Audit.Exchange will be stored in a file named 'Audit.Exchange.log'
  
  debugLogLocation - The directory you want the script logging to be stored. Ex: Exceptions, errors, etc.
  
  timeKeeperLocation -  The file path where the program will store the 'end-time' of the current run. This is used as persistent storage so that if this program misses a cycle (ex: cron job does not run properly), we can pickup the logs where we last left off.
  
### 3. .env Setup

You may use the included template to fill out the following:

Where your config file is...
O365_MANAGEMENT_API_CONFIG=C:\Users\billy\repos\o365_log_fetch\o365_logs.cfg

Where you want to store system/runtime logs (all program logs will be written to a single log file. This is NOT the file in which the O365 events will be writtern):
O365_DEBUG_LOG_LOCATION=C:\Users\billy\repos\o365_log_fetch\debug

Log level. If not defined, the default will be INFO
O365_LOG_LEVEL=INFO

