# Codebase Structure

This document describes the organization and structure of the Multi-Tenant Amazon Bedrock Agent Core Application codebase.

## Overview

The codebase follows a clean, modular architecture with clear separation between frontend, backend, infrastructure, and supporting components.

## Root Directory Structure

```
.
├── client/              # Next.js frontend application
├── server/              # FastAPI backend application
├── infra/               # Infrastructure as Code (Terraform, CDK)
├── scripts/             # Utility and setup scripts
├── docs/                # Documentation
├── data/                # Static data, media, and evaluation artifacts
├── eagle-plugin/        # Claude plugin configuration
├── .claude/             # Claude IDE configuration and commands
├── notes/               # Development notes and instructions
├── README.md            # Main project documentation
├── docker-compose.dev.yml
└── Dockerfile.backend
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

### Infrastructure (`infra/`)

Infrastructure as Code definitions for AWS resources.

```
infra/
├── terraform/          # Terraform infrastructure definitions
│   ├── main.tf         # Main resource definitions
│   ├── variables.tf    # Input variables
│   └── outputs.tf     # Output values
├── cdk/                # AWS CDK Python definitions
│   ├── app.py         # CDK application entry
│   ├── bedrock_agents.py  # Bedrock agent definitions
│   └── requirements.txt
└── eval/               # Evaluation infrastructure (CDK TypeScript)
    ├── lib/
    └── bin/
```

**Purpose:**
- Terraform: Core infrastructure (Cognito, DynamoDB, IAM)
- CDK: Bedrock Agent definitions and Lambda deployments
- Eval: Testing and evaluation infrastructure

### Scripts (`scripts/`)

Utility scripts for setup, deployment, and maintenance.

```
scripts/
├── create_bedrock_agent.py      # Bedrock agent creation
├── create_test_users_with_tiers.py  # Test user generation
├── setup_cognito_admin_groups.py     # Cognito group setup
├── setup_weather_api.py              # Weather API configuration
└── deploy-lightsail.sh               # Lightsail deployment
```

### Documentation (`docs/`)

Project documentation and guides.

```
docs/
├── codebase-structure.md    # This file
└── [additional docs]        # Other documentation files
```

### Data (`data/`)

Static data, media files, and evaluation artifacts.

```
data/
├── eval/               # Evaluation results and dashboards
├── media/              # Images, videos, diagrams
└── screenshots/        # Application screenshots
```

### Eagle Plugin (`eagle-plugin/`)

Claude IDE plugin configuration for the EAGLE acquisition assistant.

```
eagle-plugin/
├── agents/             # Agent definitions
├── commands/           # Slash command definitions
├── skills/             # Skill definitions
├── tools/              # Tool configurations
├── diagrams/           # Architecture and sequence diagrams
├── plugin.json         # Plugin manifest
└── README.md           # Plugin documentation
```

### Claude Configuration (`.claude/`)

Claude IDE configuration, commands, and expert definitions.

```
.claude/
├── commands/           # Slash commands
│   └── experts/       # Domain expert definitions
├── skills/             # Claude skills
└── settings.json       # Claude IDE settings
```

## Key Design Principles

### 1. Separation of Concerns
- **Frontend**: Client-side UI and user interactions
- **Backend**: Business logic, API endpoints, AWS integrations
- **Infrastructure**: Infrastructure definitions separate from application code

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
   - Infrastructure: Deploy via Terraform/CDK

2. **Testing**
   - Frontend: `cd client && npm test`
   - Backend: `cd server && pytest`

3. **Deployment**
   - Infrastructure: `cd infra/terraform && terraform apply`
   - Application: Use deployment scripts in `scripts/`

## File Naming Conventions

- **Python**: snake_case for files and functions
- **TypeScript/React**: PascalCase for components, camelCase for functions
- **Configuration**: kebab-case or lowercase
- **Documentation**: kebab-case.md

## Dependencies Management

- **Frontend**: `client/package.json` and `package-lock.json`
- **Backend**: `server/requirements.txt`
- **Infrastructure**: `infra/cdk/requirements.txt` (Python CDK), `infra/eval/package.json` (TypeScript CDK)

## Environment Variables

Configuration is managed through environment variables:
- Backend: `.env` file or environment variables
- Frontend: Next.js environment variables (`.env.local`)
- Infrastructure: Terraform variables or CDK context

## Notes

- The `notes/` directory contains development notes and instructions
- The `.claude/` directory contains Claude IDE-specific configuration
- The `eagle-plugin/` is a separate plugin project but included in this repository
