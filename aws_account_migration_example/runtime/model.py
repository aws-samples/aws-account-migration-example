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

import logging
from distutils.util import strtobool
from typing import List, Optional

import botocore
from boto3.session import Session
from prompt_toolkit import prompt

from aws_account_migration_example.runtime.aws import Aws
from aws_account_migration_example.runtime.validator import yes_no_validator


def get_invitation_source_and_target(invite: dict):
    source = [x for x in invite["Parties"] if x["Type"] == "ACCOUNT"]
    target = [x for x in invite["Parties"] if x["Type"] == "ORGANIZATION"]
    return (
        source[0] if len(source) > 0 else None,
        target[0] if len(target) > 0 else None,
    )


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
        if "aws" in kwargs:
            self._aws = kwargs["aws"]
        else:
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


class SourceAwsOrganization(AwsOrganization):
    child_accounts: List[dict] = []
    account_was_specified = False

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
            self.account_was_specified = True
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

    def accept_invitation(self, invitation: dict, is_quiet=False) -> Optional[str]:
        account_id = None
        source, target = get_invitation_source_and_target(invitation)
        if not is_quiet:
            confirm = prompt(
                f"Accept invite {invitation['Id']} to move account {source['Id']} to organization {target['Id']}. Proceed? (Y/N): ",
                default="N",
                validator=yes_no_validator,
            )
            if not strtobool(confirm):
                self.logger.info(f"Declining invitation {invitation['Id']}...")
                if source["Id"] == self.root_account["Id"]:
                    response_handshake = self._aws.organizations.decline_handshake(
                        HandshakeId=invitation["Id"]
                    )["Handshake"]
                    self.logger.info(
                        f"Invitation {invitation['Id']} for {source['Id']} from organization {self.organization['Id']} {response_handshake['State']}!"
                    )
                else:
                    account_scoped_aws = self._aws.account_scoped_instance(source)
                    response_handshake = (
                        account_scoped_aws.organizations.decline_handshake(
                            HandshakeId=invitation["Id"]
                        )
                    )["Handshake"]
                    self.logger.info(
                        f"Invitation {invitation['Id']} for {source['Id']} from organization {self.organization['Id']} {response_handshake['State']}!"
                    )
                return None
        if source["Id"] == self.root_account["Id"]:
            if not self.migrate_management_account(invitation, is_quiet):
                self.logger.warning("Could not delete organization.")
                return None
            self.logger.info(f"Accepting invitation {invitation['Id']}...")
            response_handshake = self._aws.organizations.accept_handshake(
                HandshakeId=invitation["Id"]
            )["Handshake"]
            account_id = source["Id"]
            self.logger.info(
                f"Invitation {invitation['Id']} for {source['Id']} from organization {self.organization['Id']} {response_handshake['State']}!"
            )
        else:
            account_scoped_aws = self._aws.account_scoped_instance(source)
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
            account_id = source["Id"]
            self.logger.info(
                f"Invitation {invitation['Id']} for {source['Id']} from organization {self.organization['Id']} {response_handshake['State']}!"
            )
        return account_id

    def __sort_invitations(self, invite):
        source, target = get_invitation_source_and_target(invite)
        if source["Id"] == self.root_account["Id"]:
            return 1
        else:
            return -1

    def accept(self, invitations: List[dict], is_quiet=False) -> [str]:
        # first sort the invitations to make sure the management account is last
        sorted_invitations = sorted(invitations, key=self.__sort_invitations)
        account_ids: [str] = []
        for invitation in sorted_invitations:
            account_id = self.accept_invitation(invitation, is_quiet)
            if account_id is not None:
                account_ids.append(account_id)
        return account_ids

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
    destination_ou: Optional[dict] = None
    root_ou: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if (
            "organizational_unit" in kwargs
            and kwargs["organizational_unit"] is not None
        ):
            organization_unit_id = kwargs["organizational_unit"]
            self.logger.info(f"Retrieving OU {organization_unit_id}")
            self.destination_ou = self._aws.organizations.describe_organizational_unit(
                OrganizationalUnitId=organization_unit_id
            )["OrganizationalUnit"]
            self.logger.info(
                f"Found OU {self.destination_ou['Id']} - {self.destination_ou['Name']}"
            )
            self.root_ou = self._aws.organizations.list_roots(MaxResults=1)["Roots"][0][
                "Id"
            ]
            self.logger.info(f"Found root OU {self.root_ou}")

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
                    if "account" in kwargs and kwargs["account"] is not None:
                        source, target = get_invitation_source_and_target(invite)
                        if kwargs["account"] == source["Id"]:
                            self.invitations.append(invite)
                    else:
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
        # if we didn't specify a single account invite the root account
        if not source.account_was_specified:
            self.send_invitation(source.root_account, is_quiet)
        return self.invitations

    def move_accounts(self, accounts: [str], is_quiet=False):
        for account in accounts:
            self.move_account(account, is_quiet)

    def move_account(self, account: str, is_quiet=False):
        if self.destination_ou is not None:
            if not is_quiet:
                confirm = prompt(
                    f"Move account {account} from root OU {self.root_ou} to destination OU {self.destination_ou['Id']} - {self.destination_ou['Name']}. Proceed? (Y/N): ",
                    default="N",
                    validator=yes_no_validator,
                )
                if not strtobool(confirm):
                    return
            self.logger.info(
                f"Moving account {account} from root OU {self.root_ou} to destination OU {self.destination_ou['Id']} - {self.destination_ou['Name']}"
            )
            self._aws.organizations.move_account(
                AccountId=account,
                SourceParentId=self.root_ou,
                DestinationParentId=self.destination_ou["Id"],
            )
