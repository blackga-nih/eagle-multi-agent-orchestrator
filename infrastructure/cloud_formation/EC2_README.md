# Eagle EC2 - GitHub Self-Hosted Runner

EC2 instance running **Amazon Linux 2023** with a baked-in **PowerUser** IAM role, intended to serve as a dev box and/or GitHub Actions self-hosted runner.

## What the Stack Creates

| Resource | Description |
|---|---|
| **IAM Role** | `power-user-eagle-ec2Role-<env>` with `PowerUserAccess` policy and permission boundary |
| **Instance Profile** | Attaches the role to the EC2 instance |
| **EC2 Key Pair** | `eagle-runner-keypair-<env>` — private key stored in SSM Parameter Store |
| **Security Group** | SSH inbound (configurable CIDR), all outbound |
| **EC2 Instance** | Amazon Linux 2023, gp3 encrypted EBS, pre-installed: git, docker, jq, AWS CLI v2 |

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `appName` | `eagle` | Application name |
| `environment` | `dev` | Environment (dev, qa, stage, prod) |
| `instanceType` | `t3.medium` | EC2 instance type |
| `vpcId` | — | VPC to launch in |
| `subnetId` | — | Subnet to launch in |
| `allowedSshCidr` | `10.0.0.0/8` | CIDR allowed for SSH |

## Connecting to the Instance

### Option 1: SSH (using stack-generated key pair)

**1. Download the private key from SSM Parameter Store:**
```bash
KEY_ID=$(aws cloudformation describe-stacks --stack-name ${APP_NAME}-ec2-${AWS_ENV} \
  --query 'Stacks[0].Outputs[?OutputKey==`KeyPairId`].OutputValue' \
  --output text --profile ${AWS_PROFILE})

aws ssm get-parameter \
  --name "/ec2/keypair/${KEY_ID}" \
  --with-decryption \
  --query 'Parameter.Value' \
  --output text --profile ${AWS_PROFILE} > ~/.ssh/${APP_NAME}-runner-${AWS_ENV}.pem

chmod 400 ~/.ssh/${APP_NAME}-runner-${AWS_ENV}.pem
```

**2. Get the instance private IP:**
```bash
IP=$(aws cloudformation describe-stacks --stack-name ${APP_NAME}-ec2-${AWS_ENV} \
  --query 'Stacks[0].Outputs[?OutputKey==`PrivateIp`].OutputValue' \
  --output text --profile ${AWS_PROFILE})
```

**3. SSH in:**
```bash
ssh -i ~/.ssh/${APP_NAME}-runner-${AWS_ENV}.pem ec2-user@${IP}
```

> **Note:** You must be on the VPN or have network connectivity to the VPC private subnet.

### Option 2: SSM Session Manager (no SSH key or inbound port needed)

Install the Session Manager plugin (macOS):
```bash
brew install --cask session-manager-plugin
```

Connect:
```bash
INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name ${APP_NAME}-ec2-${AWS_ENV} \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
  --output text --profile ${AWS_PROFILE})

aws ssm start-session --target ${INSTANCE_ID} --profile ${AWS_PROFILE}
```

## Verify PowerUser Role

Once connected, confirm the instance has the PowerUser role:
```bash
aws sts get-caller-identity
```

Test access (should succeed):
```bash
aws s3 ls
aws ec2 describe-instances --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output table
```

Test IAM is blocked (expected — PowerUser excludes IAM):
```bash
aws iam list-users   # Should return AccessDenied
```

## Pre-installed Software

The UserData bootstrap installs:
- git
- Docker (enabled and started)
- jq
- AWS CLI v2
- curl, unzip, tar, gcc, openssl-devel

A runner directory is created at `/opt/actions-runner` owned by `ec2-user`.
