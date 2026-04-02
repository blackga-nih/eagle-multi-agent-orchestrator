"""Enable Bedrock model invocation logging to CloudWatch.

Calls PutModelInvocationLoggingConfiguration to route all Bedrock
converse/invoke calls to /aws/bedrock/modelinvocations log group.

Prerequisites:
  1. Deploy core-stack first (creates log group + IAM role):
     npx cdk deploy EagleCoreStack-dev
  2. Run this script with SSO creds:
     AWS_PROFILE=eagle python scripts/enable_bedrock_logging.py

The script is idempotent — safe to run multiple times.
"""

import json
import sys

import boto3

REGION = "us-east-1"
ACCOUNT = "695681773636"
LOG_GROUP = "/aws/bedrock/modelinvocations"
ROLE_NAME = "power-user-eagle-bedrock-logging-dev"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"


def main():
    session = boto3.Session(region_name=REGION)
    bedrock = session.client("bedrock")

    # Check current config
    current = bedrock.get_model_invocation_logging_configuration()
    config = current.get("loggingConfig", {})
    if config.get("cloudWatchConfig", {}).get("logGroupName") == LOG_GROUP:
        print(f"Already enabled — logging to {LOG_GROUP}")
        print(f"  Role: {config['cloudWatchConfig'].get('roleArn')}")
        print(f"  Text delivery: {config.get('textDataDeliveryEnabled')}")
        return

    # Enable logging
    print(f"Enabling Bedrock model invocation logging...")
    print(f"  Log group: {LOG_GROUP}")
    print(f"  Role ARN:  {ROLE_ARN}")

    bedrock.put_model_invocation_logging_configuration(
        loggingConfig={
            "cloudWatchConfig": {
                "logGroupName": LOG_GROUP,
                "roleArn": ROLE_ARN,
            },
            "textDataDeliveryEnabled": True,
            "imageDataDeliveryEnabled": False,
            "embeddingDataDeliveryEnabled": False,
        }
    )

    # Verify
    verify = bedrock.get_model_invocation_logging_configuration()
    cw_config = verify.get("loggingConfig", {}).get("cloudWatchConfig", {})
    if cw_config.get("logGroupName") == LOG_GROUP:
        print("Enabled successfully.")
    else:
        print("WARNING: Config was set but verification returned unexpected result:")
        print(json.dumps(verify.get("loggingConfig", {}), indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
