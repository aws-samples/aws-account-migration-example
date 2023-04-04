from functools import partial

import boto3
import httpretty
from decorator import decorator
from moto import mock_organizations, mock_sts

from aws_account_migration_example.runtime.aws import Aws
from aws_account_migration_example.tests import date_start_end


def __organizations(session):
    organizations_client = session.client("organizations")
    organizations_client.create_organization(FeatureSet="All")
    response = organizations_client.create_account(
        Email="test@test.test",
        AccountName="Test child account",
    )
    start, end = date_start_end()

    def accept_handshake(**kwargs):
        return {
            "Handshake": {
                "Id": "string",
                "Arn": "string",
                "Parties": [
                    {"Id": "string", "Type": "ACCOUNT"},
                ],
                "State": "ACCEPTED",
                "RequestedTimestamp": start.timestamp(),
                "ExpirationTimestamp": end.timestamp(),
                "Action": "INVITE",
                "Resources": [
                    {"Value": "string", "Type": "ORGANIZATION"},
                ],
            }
        }

    def invite_account_to_organization(**kwargs):
        return {
            "Handshake": {
                "Id": "xyz",
                "Arn": "string",
                "Parties": [
                    {"Id": kwargs["Target"]["Id"], "Type": "ACCOUNT"},
                ],
                "State": "REQUESTED",
                "RequestedTimestamp": start.timestamp(),
                "ExpirationTimestamp": end.timestamp(),
                "Action": "INVITE",
                "Resources": [
                    {"Value": "string", "Type": "ORGANIZATION"},
                ],
            }
        }

    def list_handshakes_for_organization(**kwargs):
        return {"Handshakes": [], "NextToken": None}

    organizations_client.list_handshakes_for_organization = (
        list_handshakes_for_organization
    )
    organizations_client.invite_account_to_organization = invite_account_to_organization
    organizations_client.accept_handshake = accept_handshake
    return organizations_client


def __sts(session):
    sts_client = session.client("sts")
    return sts_client


def __session():
    return boto3.session.Session()


def __aws(organizations, sts):
    return Aws(organizations=organizations, sts=sts)


@decorator
def mock_aws(f, *args, **kw):
    with mock_organizations():
        with mock_sts():
            try:
                session = __session()
                organizations = __organizations(session)
                sts = __sts(session)
                aws = __aws(organizations, sts)

                def account_scoped_instance(*args, **kw):
                    return aws

                aws.account_scoped_instance = account_scoped_instance
                kw["aws"] = aws
                newf = httpretty.activate(
                    partial(f, **kw), allow_net_connect=False, verbose=True
                )
                return newf()
            finally:
                httpretty.disable()  # disable afterwards, so that you will have no problems in code that uses that socket module
                httpretty.reset()  # reset HTTPretty state (clean up registered urls and request history)
