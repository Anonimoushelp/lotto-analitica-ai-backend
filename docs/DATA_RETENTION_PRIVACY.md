# Data Retention and Privacy Controls

## Scope

This document defines the operational controls for personal data stored by the backend. It does not replace applicable Colombian privacy law, contractual obligations, or the organization's privacy notice.

## Personal data handled

The `users` table contains an email address, password hash, role, active state, and creation/update timestamps. Passwords and authentication tokens must never be stored in plaintext or written to application logs.

## Retention principles

- Retain personal data only for the period necessary for the declared service, security, accounting, legal, or audit purpose.
- Do not introduce indefinite retention by default.
- Review inactive user accounts at least annually and remove or anonymize personal identifiers when there is no continuing lawful or operational need to retain them.
- Preserve security/audit records only for the period required for their security, legal, contractual, or compliance purpose; avoid copying personal data into audit records.
- Backups inherit the same retention purpose and must be covered by the production backup lifecycle. A deleted/anonymized record is not required to be immediately recoverable from historical backups; backup expiration must eventually remove it according to the backup retention policy.

## Account deprovisioning

There is currently no public user-deletion endpoint. Account deprovisioning is therefore an administrative operation and must:

1. Disable the account (`is_active=false`) before removal or anonymization.
2. Revoke access through the existing active-user authorization check.
3. Preserve only information that is demonstrably required for security, legal, accounting, or audit purposes.
4. Remove or irreversibly anonymize the email and authentication material when no longer required.
5. Record the deprovisioning action without recording the email, password hash, token, or request payload.

Hard deletion must not be performed blindly where foreign keys or audit requirements require preservation. Prefer irreversible anonymization of the personal identifiers when an auditable record must remain.

## Data minimization and logging

- Authentication logs may contain only non-sensitive operational identifiers already approved by the security logging policy.
- Never log passwords, password hashes, bearer tokens, API keys, database URLs, or full request bodies containing personal data.
- Do not add user PII to lottery/draw records or audit metadata unless a documented business and legal purpose requires it.

## Operational review

The production owner must review this policy and inactive-account population at least annually and after any material change to authentication, auditing, backups, or data processing. Any new personal-data field requires a corresponding retention and minimization decision before production release.

## Release gate

A release that introduces a new personal-data field, endpoint, export, or persistence path is not production-ready until its purpose, access control, retention rule, deletion/anonymization behavior, logging behavior, and backup implications are documented and tested where applicable.
