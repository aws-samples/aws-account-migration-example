from aws_account_migration_example.runtime.aws import Aws
from aws_account_migration_example.runtime.model import (
    SourceAwsOrganization,
    TargetAwsOrganization,
)
from aws_account_migration_example.tests.mocks.aws.mock_aws import mock_aws


@mock_aws
def test_invite_with_single_account(aws: Aws = None):
    account = aws.organizations.list_accounts()["Accounts"][1]
    source = SourceAwsOrganization(
        profile_name="test01", account=account["Id"], aws=aws
    )
    target = TargetAwsOrganization(
        profile_name="test02", aws=aws, account=account["Id"]
    )
    invitations = target.invite(source, True)
    source.accept(invitations, True)
