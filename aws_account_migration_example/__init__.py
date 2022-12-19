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

import argparse
from distutils.util import strtobool

from prompt_toolkit import prompt

from aws_account_migration_example.model import (
    SourceAwsOrganization,
    TargetAwsOrganization,
)
from aws_account_migration_example.validator import yes_no_validator
import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger("main")
logger.setLevel("INFO")


parser = argparse.ArgumentParser(
    prog="Aws Account Migration Example",
    description="Example script from migrating all accounts from one AWS Organization to another",
    epilog="--help for more info",
)
parser.add_argument(
    "-s",
    "--source-organization-profile",
    dest="source",
    required=True,
    help="This is the profile name that has Admin access to the management account of the SOURCE AWS organization that accounts will be migrated out of to the target",
)
parser.add_argument(
    "-t",
    "--target-organization-profile",
    dest="target",
    required=True,
    help="This is the profile name that has Admin access to the management account of the TARGET AWS organization that source accounts will be migrated to",
)
parser.add_argument(
    "-a",
    "--account",
    dest="account",
    required=False,
    help="Migrate a specific account from the SOURCE AWS organization to the TARGET AWS organization",
)
parser.add_argument(
    "-q",
    "--quiet",
    dest="is_quiet",
    action="store_true",
    help="Do not prompt for confirmation",
)
args = parser.parse_args()
source = SourceAwsOrganization(profile_name=args.source, account=args.account)
target = TargetAwsOrganization(profile_name=args.target)


if not args.is_quiet:
    confirm = prompt(
        f"Migrating accounts from {source.account_details()} to {target.account_details()}. Proceed? (Y/N): ",
        default="N",
        validator=yes_no_validator,
    )
    if not strtobool(confirm):
        logger.info("Exiting...")
        parser.exit(-1, "Migration canceled")

invitations = target.invite(source, args.is_quiet)
source.accept(invitations, args.is_quiet)
parser.exit(0, "Migration complete")
