# Create the AWS Stack

**Objective**: Deploy the Eagle application infrastructure using CloudFormation templates. This collection of parameterized templates establishes the initial foundational stack pattern, which will be progressively extended to include the complete infrastructure ecosystem.  For example:

 - Common resources (ECR, IAM policies)
 - S3 buckets with encryption, versioning, and access logging
 - ECS Cluster, Task Definitions, and orchestration
 - Load Balancing Target Groups, Forwarding Rules...
 - Environment-specific configurations (dev, qa, stage, prod)

## Pre-conditions
 - AWS CLI must be installed and configured correctly
    - AWS CLI Reference: https://aws.amazon.com/cli/
    - Authentication reference: **aws configure sso**
        - Create profile named eagle
 - Basic Networking, including ALB, VPCS, CA Certs, URLs, CloudFront, F5 config, etc.
    - Reach to AWS Cloud Team via ServiceNow as needed

## Set environment
```
export APP_NAME=eagle
export AWS_PROFILE=${APP_NAME}
export AWS_ENV=dev|qa 
```

## Create AWS Common Stack
This stack creates common resources that are not environment specific (dev,qa) uch as ECR, access policy, etc.
```
aws cloudformation create-stack --stack-name ${APP_NAME}-common \
  --template-body "$(<common.yml)" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters "$(<params/common.json)" \
  --profile ${AWS_PROFILE}
```


## For each environment (dev, qa..), create APP STACK
```
# create S3
aws cloudformation create-stack --stack-name ${APP_NAME}-s3-${AWS_ENV} \
  --template-body "$(<s3.yml)" \
  --parameters "$(<params/${AWS_ENV}/s3.json)" \
  --profile ${AWS_PROFILE}
```

## Create EC2 GitHub Self-Hosted Runner
Creates an EC2 instance (Amazon Linux 2023) with a baked-in PowerUser IAM role, key pair, and security group. See [EC2_README.md](EC2_README.md) for full details and connection instructions.
```
aws cloudformation create-stack --stack-name ${APP_NAME}-ec2-${AWS_ENV} \
  --template-body "$(<ec2.yml)" \
  --parameters "$(<params/${AWS_ENV}/ec2.json)" \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile ${AWS_PROFILE}
```

## Cleanup 
```
aws cloudformation delete-stack --stack-name ${APP_NAME}-ec2-${AWS_ENV} --profile ${AWS_PROFILE}
aws cloudformation delete-stack --stack-name ${APP_NAME}-s3-${AWS_ENV} --profile ${AWS_PROFILE}
aws cloudformation delete-stack --stack-name ${APP_NAME}-common --profile ${AWS_PROFILE}
```
