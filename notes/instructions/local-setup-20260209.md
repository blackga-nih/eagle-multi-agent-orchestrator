# EAGLE Local Setup Instructions

Hey! I set you up with access to the EAGLE acquisition assistant app for testing. Here's how to get it running:

**1. Clone the repo**
```
git clone <repo-url>
cd sample-multi-tenant-agent-core-app
```

**2. Set up your `.env` file** in the project root:
```
USE_BEDROCK=true
DEV_MODE=false
REQUIRE_AUTH=true
USE_PERSISTENT_SESSIONS=false
COGNITO_USER_POOL_ID=us-east-1_AZuPs6Ifs
COGNITO_CLIENT_ID=4cv12gt73qi3nct25vl6mno72a
COGNITO_REGION=us-east-1
AWS_REGION=us-east-1
```

No Anthropic API key needed — it uses Claude through Bedrock with your AWS credentials.

**3. Make sure you have:**
- Docker installed
- AWS CLI configured (`~/.aws/credentials`) with access to us-east-1 (Bedrock, DynamoDB, S3)
- Claude Haiku model access enabled in the Bedrock console

**4. Run:**
```
docker compose -f docker-compose.dev.yml up --build
```

**5. Open** `http://localhost:3000` **and log in with:**
- Email: `hoquemi@nih.gov`
- Password: *(sent separately via DM)*

Let me know if you hit any issues!
