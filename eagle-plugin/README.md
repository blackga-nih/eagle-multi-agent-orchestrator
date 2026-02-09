# EAGLE Plugin - NCI Acquisition Assistant

**E**nterprise **A**cquisitions **G**uidance & **L**ogistics **E**ngine

A unified OpenClaw plugin for the NCI Office of Acquisitions, combining the best practices from federal acquisition expertise into a single-agent architecture with specialized skills.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    EAGLE Supervisor Agent                    │
│                  (Intent Detection & Routing)                │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   OA Intake   │    │   Document    │    │  Compliance   │
│    Skill      │    │   Generator   │    │    Skill      │
└───────────────┘    └───────────────┘    └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐
│  Knowledge    │    │  Tech Review  │
│  Retrieval    │    │    Skill      │
└───────────────┘    └───────────────┘
```

## Prerequisites

### Required Environment Variables

The plugin uses Claude Code's tools to interact with AWS. Set these in your environment:

```bash
# AWS Credentials (for S3 document storage, DynamoDB intake tracking)
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

# Or use AWS CLI configuration
aws configure
```

### AWS Resources Needed

| Resource | Purpose | Required |
|----------|---------|----------|
| S3 Bucket | Document storage (SOW, IGCE, etc.) | Yes |
| DynamoDB Table | Intake record tracking | Optional |
| CloudWatch Logs | Activity logging | Optional |

**Minimal Setup (S3 only):**
```bash
# Create an S3 bucket for documents
aws s3 mb s3://your-eagle-documents --region us-east-1
```

**Full Setup:**
```bash
# S3 bucket
aws s3 mb s3://your-eagle-documents --region us-east-1

# DynamoDB table (single-table design)
aws dynamodb create-table \
  --table-name eagle \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### IAM Permissions

The AWS user/role needs these permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::your-eagle-documents", "arn:aws:s3:::your-eagle-documents/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:UpdateItem"],
      "Resource": "arn:aws:dynamodb:*:*:table/eagle"
    }
  ]
}
```

### No API Key Needed in Plugin

The plugin is just markdown instructions. Claude Code handles the Anthropic API key separately via:
- `ANTHROPIC_API_KEY` environment variable, or
- Claude Code's built-in authentication

---

## Quick Start

### Slash Commands

| Command | Description |
|---------|-------------|
| `/intake` | Start a new acquisition request |
| `/document <type>` | Generate SOW, IGCE, AP, or J&A |
| `/search <query>` | Search FAR/DFAR regulations |
| `/status` | Check intake package completeness |

### Example Conversations

**Starting an Acquisition:**
```
User: I need to purchase a CT scanner for our research facility
EAGLE: I can help with that! Let me ask a few questions...
       - What's the estimated cost?
       - When do you need it?
       - Do you have a specific vendor in mind?
```

**Searching Regulations:**
```
User: /search sole source justification requirements
EAGLE: Found 5 relevant FAR sections...
       1. FAR 6.302 - Circumstances Permitting Other Than Full Competition
       2. FAR 6.303 - Justifications (J&A)
       ...
```

## Plugin Structure

```
eagle-plugin/
├── plugin.json                     # Plugin manifest
├── README.md                       # This documentation
│
├── agent/
│   └── supervisor.md               # Single orchestrator agent
│
├── skills/
│   ├── oa-intake/
│   │   └── SKILL.md               # Acquisition intake workflow
│   ├── document-generator/
│   │   └── SKILL.md               # SOW, IGCE, AP, J&A generation
│   ├── compliance/
│   │   └── SKILL.md               # FAR/DFAR compliance, vehicle search
│   ├── knowledge-retrieval/
│   │   └── SKILL.md               # Knowledge base search
│   └── tech-review/
│       └── SKILL.md               # Technical requirements validation
│
├── commands/
│   ├── intake.md                  # /intake slash command
│   ├── document.md                # /document slash command
│   ├── search.md                  # /search slash command
│   └── status.md                  # /status slash command
│
├── data/
│   ├── far-database.json          # 53+ FAR entries
│   ├── thresholds.json            # Dollar thresholds
│   ├── contract-vehicles.json     # NIH IDIQs, GSA schedules, BPAs
│   └── templates/
│       ├── sow-template.md
│       ├── igce-template.md
│       ├── acquisition-plan-template.md
│       ├── justification-template.md
│       └── market-research-template.md
│
└── tools/
    └── tool-definitions.json      # Anthropic tool_use format definitions
```

## Skills Overview

### OA Intake
Guides users through the acquisition intake process like a knowledgeable contract specialist ("Trish" philosophy). Collects minimal information upfront, asks smart follow-ups, and determines the optimal acquisition pathway.

### Document Generator
Creates acquisition documents including:
- Statement of Work (SOW)
- Independent Government Cost Estimate (IGCE)
- Acquisition Plan (FAR 7.105)
- Justification & Approval (J&A)
- Market Research Report

### Compliance
Ensures FAR/DFAR compliance by:
- Searching the regulation database
- Identifying required clauses
- Recommending contract vehicles
- Checking socioeconomic requirements

### Knowledge Retrieval
Searches the knowledge base for:
- Policies and procedures
- Past acquisition precedents
- Regulatory guidance
- Technical documentation

### Tech Review
Validates technical requirements:
- Specification completeness
- Installation requirements
- Training/support needs
- Section 508 accessibility

## Key Thresholds

| Threshold | Amount | Significance |
|-----------|--------|--------------|
| Micro-Purchase (MPT) | $10,000 | Minimal documentation, purchase card |
| Simplified (SAT) | $250,000 | FAR Part 13 procedures |
| Sole Source 8(a) Services | $4,500,000 | Competition required above |
| Sole Source 8(a) Manufacturing | $7,000,000 | Competition required above |
| Cost/Pricing Data (TINA) | $2,000,000 | Certified data required |
| Major Acquisition Plan | $7,000,000 | Written AP required |

## Integration

### AWS Services
- **S3**: Document storage (`nci-documents` bucket)
- **DynamoDB**: Intake tracking (`eagle` table)

### API Tools
All tools follow the Anthropic `tool_use` format for seamless Claude integration. See `tools/tool-definitions.json` for the complete schema.

## Philosophy: "Think Like Trish"

This plugin embodies the expertise of a senior contracting officer who:
1. **Starts minimal** - Collects just enough information to begin
2. **Asks smart follow-ups** - Based on user answers, not a rigid form
3. **Determines the path** - Acquisition type and required documents
4. **Guides to completion** - Helps generate each required document
5. **Documents everything** - Maintains defensible decision rationale

## Contributing

See the main repository README for contribution guidelines.

## License

Internal NCI use only. All rights reserved.
