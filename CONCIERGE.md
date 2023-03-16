# Steps for AWS Concierge

## Steps to assure the accounts are ready to become a standalone account (mandatory for the migration)
1. Customer should change all linked accounts phone numbers to the payer's (verified) phone, this can be done through CLI. This steps is important to avoid having to make multiple phone calls for the phone verification step.
1. Concierge will verify all accounts manually to change their status from phone unverified to phone verified.
1. With the customer's authorization, Concierge will change all account payment methods to the payers payment method.
## Things to consider prior to the migration:
1. Assure tax inheritance is enabled on all payers (if possible)
1. Assure the new payer as well as all the old payers have the CUR enabled (and backfilled if needed)
1. Check billing preferences on the new payer for credit sharing and RI/SP discount sharing
1. Assure the new payer has the appropriate Organizations Linked Account limit and Cscore