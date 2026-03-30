# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in EAGLE, please report it to the NCI CBIIT security team. Do not open a public GitHub issue for security vulnerabilities.

**Contact**: NCI CBIIT Security Team via your organization's security reporting channel.

## Security Scope

EAGLE handles sensitive acquisition data. Key security boundaries:

| Component | Mechanism |
|-----------|-----------|
| **Authentication** | AWS Cognito JWT tokens with tenant_id, user_id, and subscription_tier claims |
| **Tenant Isolation** | DynamoDB partition keys scoped by tenant_id; session IDs encode tenant context |
| **Document Storage** | S3 with server-side encryption; bucket policies restrict cross-tenant access |
| **Network** | ALBs are VPC-internal; no public internet exposure. Access via VPN or SSM |
| **Model Access** | Amazon Bedrock with IAM role-based access; no API keys in client code |

## Important Disclaimers

This is a reference implementation. Production deployments require:

- Comprehensive security review and penetration testing
- Rate limiting and DDoS protection
- Encryption at rest and in transit verification
- Compliance review (FISMA, NIST 800-53, etc.)
- Monitoring, alerting, and incident response procedures

See the [README disclaimers](README.md#important-disclaimers) for the full list.
