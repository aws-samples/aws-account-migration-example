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

from typing import List, Optional
from aws_account_migration_example.aws import Aws
from boto3.session import Session
import botocore
import logging
from aws_account_migration_example.validator import yes_no_validator
from distutils.util import strtobool
from prompt_toolkit import prompt


class AwsOrganization:
    profile: str
    root_account: dict
    organization: dict
    _aws: Aws
    logger: logging.Logger

    def __init__(self, **kwargs):
        self.logger = logging.getLogger(kwargs["profile_name"])
        self.logger.setLevel(logging.INFO)
        self.logger.info(
            f" Retrieving source organization and account information using profile {kwargs['profile_name']}"
        )
        session = Session(profile_name=kwargs["profile_name"])
        self._aws = Aws(session=session)
        self.organization = self._aws.organizations.describe_organization()[
            "Organization"
        ]
        self.root_account = self._aws.organizations.describe_account(
            AccountId=self.organization["MasterAccountId"]
        )["Account"]
        self.logger.info(f" Source account is {self.account_details()}")

    def account_details(self):
        return f"{self.organization['Id']} - {self.root_account['Id']} - {self.root_account['Email']}"

    def get_invitation_source_and_target(self, invite: dict):
        source = [x for x in invite["Parties"] if x["Type"] == "ACCOUNT"]
        target = [x for x in invite["Parties"] if x["Type"] == "ORGANIZATION"]
        return (
            source[0] if len(source) > 0 else None,
            target[0] if len(target) > 0 else None,
        )


class SourceAwsOrganization(AwsOrganization):
    child_accounts: List[dict] = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if "account" in kwargs and kwargs["account"] is not None:
            self.logger.info(
                f"Retrieving child account {kwargs['account']} for management account {self.account_details()}"
            )
            response = self._aws.organizations.describe_account(
                AccountId=kwargs["account"]
            )
            self.child_accounts.append(response["Account"])
        else:
            self.logger.info(
                f"Retrieving all child accounts for management account {self.account_details()}"
            )
            list_accounts_iterator = self._aws.list_accounts.paginate(
                PaginationConfig={
                    "PageSize": 10,
                }
            )
            for page in list_accounts_iterator:
                for account in page["Accounts"]:
                    if account["Id"] != self.root_account["Id"]:
                        self.child_accounts.append(account)

    def accept_invitation(self, invitation: dict, is_quiet=False):
        source, target = self.get_invitation_source_and_target(invitation)
        if not is_quiet:
            confirm = prompt(
                f"Accept invite {invitation['Id']} to move account {source['Id']} to organization {target['Id']}. Proceed? (Y/N): ",
                default="N",
                validator=yes_no_validator,
            )
            if not strtobool(confirm):
                self.logger.info(f"Declining invitation {invitation['Id']}...")
                self._aws.organizations.decline_handshake(HandshakeId=invitation["Id"])
                return
        if source["Id"] == self.root_account["Id"]:
            if not self.migrate_management_account(invitation, is_quiet):
                self.logger.warning("Could not delete organization.")
                return
            self.logger.info(f"Accepting invitation {invitation['Id']}...")
            response_handshake = self._aws.organizations.accept_handshake(
                HandshakeId=invitation["Id"]
            )["Handshake"]
        else:
            response = self._aws.sts.assume_role(
                RoleArn=f"arn:aws:iam::{source['Id']}:role/AwsAccountMigrationAcceptInvitationRole",
                RoleSessionName="aws-account-migration-example",
            )
            credentials = response["Credentials"]
            session = Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
            account_scoped_aws = Aws(session=session)
            self.logger.info(
                f"Removing {source['Id']} from organization {self.organization['Id']}..."
            )
            response = self._aws.organizations.remove_account_from_organization(
                AccountId=source["Id"]
            )
            self.logger.info(f"Accepting invitation {invitation['Id']}...")
            response_handshake = account_scoped_aws.organizations.accept_handshake(
                HandshakeId=invitation["Id"]
            )["Handshake"]
        self.logger.info(
            f"Invitation {invitation['Id']} for {source['Id']} from organization {self.organization['Id']} {response_handshake['State']}!"
        )

    def __sort_invitations(self, invite):
        source, target = self.get_invitation_source_and_target(invite)
        if source["Id"] == self.root_account["Id"]:
            return 1
        else:
            return -1

    def accept(self, invitations: List[dict], is_quiet=False):
        # first sort the invitations to make sure the management account is last
        sorted_invitations = sorted(invitations, key=self.__sort_invitations)
        for invitation in sorted_invitations:
            self.accept_invitation(invitation, is_quiet)

    def migrate_management_account(self, invitation: dict, is_quiet=False):
        if not is_quiet:
            confirm = prompt(
                f"Delete AWS organization {self.organization['Id']}? (Y/N): ",
                default="N",
                validator=yes_no_validator,
            )
            if not strtobool(confirm):
                self.logger.info(f"Skipping deletion of organization.")
                return False
        self.logger.info(f"Deleting organization {self.organization['Id']}")
        self._aws.organizations.delete_organization()
        self.logger.info(f"Organization {self.organization['Id']} deleted")
        return True


class TargetAwsOrganization(AwsOrganization):
    invitations: List[dict] = []
    organization_id: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger.info(
            f"Retrieving existing invitations for management account {self.account_details()}"
        )
        handshakes_iterator = self._aws.list_handshakes_for_organization.paginate(
            Filter={"ActionType": "INVITE"},
            PaginationConfig={
                "PageSize": 10,
            },
        )
        for page in handshakes_iterator:
            for invite in page["Handshakes"]:
                if invite["State"] == "OPEN":
                    self.invitations.append(invite)

    def send_invitation(self, account: dict, is_quiet=False):
        if not is_quiet:
            confirm = prompt(
                f"Invite account {account['Id']} to {self.account_details()}. Proceed? (Y/N): ",
                default="N",
                validator=yes_no_validator,
            )
            if not strtobool(confirm):
                self.logger.info(f"Skipping account {account['Id']}...")
                return
        self.logger.info(f"Inviting account {account['Id']}")
        try:
            response = self._aws.organizations.invite_account_to_organization(
                Target={"Id": account["Id"], "Type": "ACCOUNT"},
                Notes="Invite generated by AWS Account Migration Example Script",
            )
            self.invitations.append(response["Handshake"])
        except botocore.exceptions.ClientError as error:
            if error.response["Error"]["Code"] == "DuplicateHandshakeException":
                self.logger.warning("Invitation already sent...")
            else:
                raise error

    def invite(self, source: SourceAwsOrganization, is_quiet=False):
        for account in source.child_accounts:
            self.send_invitation(account, is_quiet)
        # If we've passed in a single account to be moved and that account is not the management account don't try to move the management account
        if (
            len(source.child_accounts) == 1
            and source.child_accounts[0] != source.root_account["Id"]
        ) or len(source.child_accounts) > 1:
            self.send_invitation(source.root_account, is_quiet)
        return self.invitations
