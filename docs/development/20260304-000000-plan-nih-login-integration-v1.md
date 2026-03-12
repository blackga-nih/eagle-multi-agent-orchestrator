# EAGLE — NIH Login Integration Plan

**Date:** 2026-03-04
**From:** EAGLE Engineering Team
**To:** Rene (NIH IT / IAM)
**Type:** Technical Coordination Document

---

## Executive Summary

EAGLE is an internal NCI AI acquisition assistant running on AWS ECS Fargate in the NCI AWS account (`695681773636`). Authentication currently routes through an AWS Cognito User Pool. This document describes the steps required from NIH IT and from the EAGLE team to federate that Cognito pool with NIH Login via SAML 2.0, so that NCI staff can sign in using their existing NIH credentials — no separate account required.

---

## 1. Overview

| Item | Value |
|------|-------|
| Application | EAGLE — NCI AI Acquisition Assistant |
| AWS Account | `695681773636` (NCI) |
| Runtime | AWS ECS Fargate, us-east-1 |
| Current Auth | AWS Cognito User Pool `us-east-1_ChGLHtmmp` |
| Target Auth | NIH Login federated into Cognito via SAML 2.0 |
| Network | All ALBs are internal (VPC-only); accessible from NIH VPN/network only |

The integration federate NIH Login as a SAML 2.0 Identity Provider (IdP) into the existing Cognito User Pool. Once complete, NCI staff will click "Sign in with NIH Login" on the EAGLE login page, authenticate through NIH's existing SSO flow, and receive a Cognito JWT that the EAGLE backend validates — no duplicate credential management.

---

## 2. What We Need from NIH IT

### 2.1 SAML IdP Metadata

One of the following:

- A **metadata URL** that Cognito can poll (preferred — simplifies key rotation), or
- A **static SAML 2.0 metadata XML file** for manual upload to Cognito

### 2.2 SP Registration

Please register EAGLE as a SAML Service Provider with the following parameters:

| Parameter | Value |
|-----------|-------|
| SP Entity ID | `urn:amazon:cognito:sp:us-east-1_ChGLHtmmp` |
| ACS URL (HTTP-POST binding) | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_ChGLHtmmp/saml2/idpresponse` |
| NameID Format | `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` (preferred) or `email` |
| Binding | HTTP-POST |
| Requested Attributes | `email`, `givenName`, `familyName` (required); NIH username or IC/org code (optional — used for tenant mapping) |

### 2.3 Process Requirements

- Approval through any required ISRA or ATO process applicable to this application
- Confirmation of any IP restrictions on the SAML IdP endpoint (EAGLE's ECS tasks run on NCI VPC IPs in `vpc-09def43fcabfa4df6`)

---

## 3. What We Will Do (EAGLE Team)

Once NIH IT delivers the SAML metadata, our work is approximately 1–2 days of CDK changes:

1. Add NIH Login as a SAML Identity Provider on the Cognito User Pool (via AWS CDK)
2. Map SAML attributes to Cognito user attributes:

| SAML Attribute | Cognito Attribute |
|----------------|-------------------|
| `email` | `email` |
| `givenName` | `given_name` |
| `familyName` | `family_name` |
| NIH IC / org code (if provided) | `custom:tenant_id` |

3. Configure the Cognito App Client to accept the SAML IdP flow and set the correct callback URLs
4. Add the Cognito-hosted UI callback URL to the ALB listener rules if required
5. Deploy changes via GitHub Actions to the NCI account (`695681773636`)
6. Revert `DEV_MODE` from `true` to `false` on the ECS task (see Section 6)

---

## 4. Auth Flow

```
User (NIH workstation or VPN)
  │
  │  HTTPS — NIH internal network only
  ▼
Internal ALB (VPC-only)
  │
  ▼
Next.js Frontend (ECS Fargate)
  │
  │  Redirect to Cognito Hosted UI
  ▼
Cognito Hosted UI  ──────────────────────────────────────────────────────────┐
  │                                                                          │
  │  SAML AuthnRequest (HTTP-POST)                                          │
  ▼                                                                          │
NIH Login SAML IdP                                                           │
  │                                                                          │
  │  SAML Response with assertions (email, name, org)                       │
  └──────────────────────────────────────────────────────────────────────► Cognito
                                                                             │
                                                                             │  JWT (id_token + access_token)
                                                                             ▼
                                                              Next.js Frontend (stores token)
                                                                             │
                                                                             │  Authorization: Bearer <JWT>
                                                                             ▼
                                                              FastAPI Backend (ECS Fargate)
                                                                             │
                                                                             │  Validates JWT against Cognito JWKS
                                                                             ▼
                                                                      Authorized Response
```

All traffic remains within the NIH network. The NIH Login SAML IdP endpoint must be reachable from NCI VPC IPs — please confirm there are no IP allowlist requirements on the IdP side.

---

## 5. Timeline Estimate

| Phase | Owner | Duration |
|-------|-------|----------|
| SP registration + metadata delivery | NIH IT | 1–2 weeks |
| CDK changes (Cognito SAML IdP + attribute mapping) | EAGLE team | 1–2 days |
| Integration testing (VPN access, attribute flow, token validation) | EAGLE team + NIH IT | 1 day |
| **Total** | | **~2–3 weeks end to end** |

The critical path is the SP registration on NIH IT's side. EAGLE team can begin CDK scaffolding in parallel and deploy within one day of metadata delivery.

---

## 6. Current Interim State

| Setting | Current Value | Post-Integration Value |
|---------|---------------|------------------------|
| `DEV_MODE` (ECS task env var) | `true` — auth bypassed | `false` — full JWT enforcement |
| Access control | NIH VPN network boundary only | NIH VPN + NIH Login authentication |
| User accounts | None required | NIH credentials (no separate account) |

The application is currently accessible only from the NIH network due to the internal ALB configuration. `DEV_MODE=true` is a temporary development posture that will be reverted to `false` immediately after NIH Login is verified end-to-end.

---

## 7. Questions for NIH IT

1. Does NIH provide a SAML 2.0 **metadata URL** we can point Cognito at directly, or do we need to download and upload a static XML file? (A URL is strongly preferred — it handles key rotation automatically.)

2. What **attributes** does NIH Login assert in the SAML response? At minimum we need `email`, `givenName`, and `familyName`. If an IC or organizational unit code is available, we would use it for tenant routing.

3. Is there an **existing registered SAML SP for an AWS Cognito pool** we can reference or clone? This would accelerate the registration process significantly.

4. What is the **SP registration process** — ISRA submission, helpdesk ticket, or direct contact with the IAM team?

5. Are there **IP restrictions** on the NIH Login SAML IdP endpoint? Our ECS tasks run on NCI VPC IPs (`vpc-09def43fcabfa4df6`, subnets in `10.209.140.192/26`). If the IdP allowlists by IP we will need those ranges added.

---

## 8. Reference

| Resource | Value |
|----------|-------|
| Cognito User Pool ID | `us-east-1_ChGLHtmmp` |
| AWS Region | `us-east-1` |
| NCI AWS Account | `695681773636` |
| NCI VPC | `vpc-09def43fcabfa4df6` |
| ECS Cluster | `eagle-dev` |
| SP Entity ID | `urn:amazon:cognito:sp:us-east-1_ChGLHtmmp` |
| ACS URL | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_ChGLHtmmp/saml2/idpresponse` |
| AWS Cognito SAML docs | https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-saml-idp.html |

---

*Scribe | 2026-03-04T00:00:00Z | Format: markdown | Type: plan*
