#  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy of this
#  software and associated documentation files (the "Software"), to deal in the Software
#  without restriction, including without limitation the rights to use, copy, modify,
#  merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  permit persons to whom the Software is furnished to do so.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#  INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
#  PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#  OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#  SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import boto3
from boto3.session import Session
from botocore.config import Config


class Aws:
    def __init__(self, **kwargs):

        self.session = (
            kwargs["session"] if "session" in kwargs else boto3.session.Session()
        )
        default_config = Config(retries={"max_attempts": 3, "mode": "standard"})
        self.organizations = (
            kwargs["organizations"]
            if "organizations" in kwargs
            else self.session.client("organizations", config=default_config)
        )
        self.list_accounts = self.organizations.get_paginator("list_accounts")
        self.list_handshakes_for_organization = self.organizations.get_paginator(
            "list_handshakes_for_organization"
        )
        self.sts = (
            kwargs["sts"]
            if "sts" in kwargs
            else self.session.client("sts", config=default_config)
        )


    def account_scoped_instance(self, source):
        response = self.sts.assume_role(
            RoleArn=f"arn:aws:iam::{source['Id']}:role/AwsAccountMigrationAcceptInvitationRole",
            RoleSessionName="aws-account-migration-example",
        )
        credentials = response["Credentials"]
        session = Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )
        return Aws(session=session)
