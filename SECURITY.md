# Security policy

Do not open a public issue containing credentials, private URLs, personal data or unpublished
evidence. Revoke exposed credentials immediately. Until a private reporting channel is published,
contact the repository owner through their GitHub profile and disclose only enough information to
establish a secure reporting route.

The catalogue stores metadata locally in SQLite. It is not a secrets store. Connector credentials
must be supplied through the environment or an external secrets manager and must never be written to
catalogue exports or logs.

