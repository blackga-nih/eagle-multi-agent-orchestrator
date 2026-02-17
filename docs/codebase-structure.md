# Codebase Structure

This document describes the organization and structure of the Multi-Tenant Amazon Bedrock Agent Core Application codebase.

## Overview

The codebase follows a clean, modular architecture with clear separation between frontend, backend, infrastructure, deployment, and supporting components.

## Root Directory Structure

```
.
├── client/              # Next.js frontend application
├── server/              # FastAPI backend application
├── infrastructure/      # Infrastructure as Code (Terraform, CDK)
├── deployment/          # Deployment scripts, Docker files, and configs
├── docs/                # Centralized documentation
├── data/                # Static data, media, and evaluation artifacts
├── eagle-plugin/        # EAGLE plugin configuration (single source of truth)
├── tools/               # Development tools and utilities
├── .claude/             # Claude IDE configuration and commands
├── .github/             # GitHub Actions workflows
├── README.md            # Main project documentation
└── .gitignore           # Git ignore rules
```

## Component Details

### Client (`client/`)

Next.js 14+ application with TypeScript, providing the user interface for the multi-tenant chat application.

```
client/
├── app/                 # Next.js App Router pages and API routes
│   ├── admin/          # Admin dashboard pages
│   ├── api/            # Next.js API route handlers
│   ├── chat-advanced/  # Advanced chat interface
│   ├── documents/      # Document management pages
│   ├── login/          # Authentication pages
│   └── workflows/      # Workflow management
├── components/         # React components
│   ├── agents/        # Agent-related components
│   ├── auth/          # Authentication components
│   ├── chat/          # Chat interface components
│   ├── documents/     # Document components
│   ├── forms/         # Form components
│   ├── layout/        # Layout components
│   └── ui/            # Reusable UI components
├── contexts/          # React context providers
├── hooks/             # Custom React hooks
├── lib/               # Utility libraries and helpers
├── types/             # TypeScript type definitions
├── tests/             # Playwright end-to-end tests
├── public/            # Static assets
└── [config files]     # Next.js, TypeScript, Tailwind configs
```

**Key Files:**
- `package.json` - Node.js dependencies and scripts
- `next.config.mjs` - Next.js configuration
- `tsconfig.json` - TypeScript configuration
- `tailwind.config.ts` - Tailwind CSS configuration

### Server (`server/`)

FastAPI backend application handling authentication, Bedrock Agent Core integration, and business logic.

```
server/
├── app/                # Application modules
│   ├── auth.py         # Authentication utilities
│   ├── bedrock_service.py      # Bedrock Agent Core integration
│   ├── cognito_auth.py         # Cognito JWT validation
│   ├── session_store.py        # DynamoDB session management
│   ├── cost_attribution.py     # Cost tracking and attribution
│   ├── subscription_service.py # Subscription tier management
│   ├── admin_service.py        # Admin operations
│   ├── agentic_service.py      # Agent orchestration
│   ├── streaming_routes.py     # WebSocket streaming
│   └── main.py         # FastAPI application entry point
├── tests/              # Backend unit and integration tests
├── config.py           # Configuration management
├── requirements.txt    # Python dependencies
└── run.py              # Development server entry point
```

**Key Files:**
- `requirements.txt` - Python package dependencies
- `config.py` - Environment configuration
- `run.py` - Development server launcher

### Infrastructure (`infrastructure/`)

Infrastructure as Code definitions for AWS resources.

```
infrastructure/
├── cdk-eagle/          # EAGLE CDK TypeScript stacks (primary)
│   ├── bin/eagle.ts   # CDK app entry — instantiates all stacks
│   ├── lib/
│   │   ├── core-stack.ts      # VPC, Cognito, IAM, S3/DDB imports
│   │   ├── compute-stack.ts   # ECS Fargate, ECR, ALB
│   │   └── cicd-stack.ts      # OIDC + GitHub Actions role
│   ├── config/
│   │   └── environments.ts    # Per-env config (dev, staging, prod)
│   ├── cdk.json
│   ├── tsconfig.json
│   └── package.json
├── cdk/                # DEPRECATED — Python reference stack (not deployed)
├── terraform/          # Terraform infrastructure definitions
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── eval/               # Evaluation observability (CDK TypeScript)
    ├── lib/eval-stack.ts
    └── bin/
```

**Purpose:**
- CDK-Eagle: Primary infrastructure — VPC, Cognito, ECS Fargate, OIDC
- Terraform: Legacy core infrastructure reference
- Eval: CloudWatch dashboards, alarms, S3 artifacts
- CDK (old): Deprecated Python reference — see `DEPRECATED.md`

### Deployment (`deployment/`)

Deployment scripts, Docker configurations, and deployment orchestration.

```
deployment/
├── docker/                          # Docker files
│   ├── Dockerfile.backend           # Backend Docker image (ECS Fargate)
│   └── Dockerfile.frontend          # Frontend Docker image (Next.js standalone)
├── docker-compose.dev.yml           # Local development compose
└── scripts/                         # Deployment and setup scripts
    ├── create_bedrock_agent.py      # Bedrock agent creation
    ├── create_test_users_with_tiers.py  # Test user generation
    ├── setup_cognito_admin_groups.py     # Cognito group setup
    ├── setup_weather_api.py              # Weather API configuration
    └── deploy-lightsail.sh               # Lightsail deployment
```

### Documentation (`docs/`)

Centralized project documentation.

```
docs/
├── architecture/        # Architecture docs, diagrams, reference documents
│   ├── diagrams/       # Mermaid and Excalidraw diagrams
│   ├── orchestration/  # SDK/Bedrock orchestration docs
│   └── reference-documents/  # AP exhibits, design docs, use cases
├── deployment/          # Deployment guides and validation checklists
├── development/         # Development setup, meeting transcripts
│   ├── local-setup-20260209.md
│   ├── meeting-transcripts/
│   └── screenshots/
├── api/                 # API documentation
├── codebase-structure.md    # This file
├── restructuring-plan.md    # Restructuring plan
└── claude-merge-analysis-workflow.md
```

### Data (`data/`)

Static data, media files, and evaluation artifacts.

```
data/
├── eval/               # Evaluation results, telemetry, dashboards, videos
├── media/              # Images, videos, diagrams
└── screenshots/        # Application screenshots
```

### Eagle Plugin (`eagle-plugin/`)

EAGLE plugin configuration — single source of truth for agent and skill definitions.

```
eagle-plugin/
├── agents/             # 8 agent directories with agent.md + YAML frontmatter
├── skills/             # 5 skill directories with SKILL.md + YAML frontmatter
├── commands/           # Slash command definitions
├── tools/              # Tool configurations
├── diagrams/           # Architecture and sequence diagrams
├── plugin.json         # Plugin manifest
└── README.md           # Plugin documentation
```

### Tools (`tools/`)

Development tools and utilities.

```
tools/
├── doc-export/         # PDF and Word document export utilities
├── scripts/            # Utility scripts
└── configs/            # Tool configurations
```

### Claude Configuration (`.claude/`)

Claude IDE configuration, commands, and expert definitions.

```
.claude/
├── commands/           # Slash commands
│   └── experts/       # Domain expert definitions (9 experts)
├── skills/             # Claude skills
├── specs/              # Implementation specs
└── settings.json       # Claude IDE settings
```

## Key Design Principles

### 1. Separation of Concerns
- **Frontend**: Client-side UI and user interactions
- **Backend**: Business logic, API endpoints, AWS integrations
- **Infrastructure**: Infrastructure definitions separate from application code
- **Deployment**: Docker, scripts, and deployment configs isolated from source

### 2. Modularity
- Components organized by feature/domain
- Reusable utilities in `lib/` directories
- Clear interfaces between layers

### 3. Type Safety
- TypeScript for frontend with strict type checking
- Pydantic models for backend data validation
- Type definitions in dedicated `types/` directories

### 4. Testability
- Frontend: Playwright end-to-end tests
- Backend: Unit and integration tests
- Test utilities and fixtures organized with source code

### 5. Configuration Management
- Environment-based configuration
- Infrastructure variables in IaC files
- Secrets and credentials via environment variables

## Technology Stack

### Frontend
- **Framework**: Next.js 14+ (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Testing**: Playwright
- **State Management**: React Context API

### Backend
- **Framework**: FastAPI
- **Language**: Python 3.11+
- **AWS SDK**: boto3
- **Authentication**: PyJWT, Cognito
- **Testing**: pytest (implied)

### Infrastructure
- **IaC**: Terraform, AWS CDK
- **Cloud Provider**: AWS
- **Services**: Bedrock, Cognito, DynamoDB, IAM

## Development Workflow

1. **Local Development**
   - Frontend: `cd client && npm run dev`
   - Backend: `cd server && python run.py`
   - Docker: `cd deployment && docker compose -f docker-compose.dev.yml up`
   - Infrastructure: Deploy via Terraform/CDK

2. **Testing**
   - Frontend: `cd client && npm test`
   - Backend: `cd server && pytest`

3. **Deployment**
   - Infrastructure: `cd infrastructure/terraform && terraform apply`
   - Application: Use deployment scripts in `deployment/scripts/`

## File Naming Conventions

- **Python**: snake_case for files and functions
- **TypeScript/React**: PascalCase for components, camelCase for functions
- **Configuration**: kebab-case or lowercase
- **Documentation**: kebab-case.md

## Dependencies Management

- **Frontend**: `client/package.json` and `package-lock.json`
- **Backend**: `server/requirements.txt`
- **Infrastructure**: `infrastructure/cdk/requirements.txt` (Python CDK), `infrastructure/eval/package.json` (TypeScript CDK)

## Environment Variables

Configuration is managed through environment variables:
- Backend: `.env` file or environment variables
- Frontend: Next.js environment variables (`.env.local`)
- Infrastructure: Terraform variables or CDK context

## Notes

- The `.claude/` directory contains Claude IDE-specific configuration
- The `eagle-plugin/` is the single source of truth for agent/skill definitions
- The `tools/` directory contains development utilities (doc-export, configs)
- The `data/` directory contains evaluation results and media assets (gitignored on main)
