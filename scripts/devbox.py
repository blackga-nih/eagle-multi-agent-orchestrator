#!/usr/bin/env python3
"""
devbox.py — EC2 dev box lifecycle manager.

Looks up the instance from CloudFormation stack 'eagle-ec2-dev' automatically.
No instance ID required.

Usage:
  python scripts/devbox.py status
  python scripts/devbox.py start
  python scripts/devbox.py stop
  python scripts/devbox.py ssm
"""

import subprocess
import sys

import boto3

STACK_NAME = "eagle-ec2-dev"
REGION = "us-east-1"


def get_stack_outputs() -> dict:
    cf = boto3.client("cloudformation", region_name=REGION)
    try:
        resp = cf.describe_stacks(StackName=STACK_NAME)
        outputs = resp["Stacks"][0].get("Outputs", [])
        return {o["OutputKey"]: o["OutputValue"] for o in outputs}
    except cf.exceptions.ClientError as e:
        if "does not exist" in str(e):
            print(f"Stack '{STACK_NAME}' not found.")
            print("Deploy it first: aws cloudformation deploy \\")
            print("  --template-file aws/cloud_formation/ec2.yml \\")
            print("  --stack-name eagle-ec2-dev \\")
            print("  --parameter-overrides file://aws/cloud_formation/params/dev/ec2.json \\")
            print("  --capabilities CAPABILITY_NAMED_IAM")
            sys.exit(1)
        raise


def get_instance_state(ec2, instance_id: str) -> str:
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    return resp["Reservations"][0]["Instances"][0]["State"]["Name"]


def cmd_status():
    outputs = get_stack_outputs()
    instance_id = outputs.get("InstanceId")
    private_ip = outputs.get("PrivateIp", "unknown")
    ssm_path = outputs.get("PrivateKeySsmPath", "unknown")

    ec2 = boto3.client("ec2", region_name=REGION)
    state = get_instance_state(ec2, instance_id)

    print(f"Dev box:     {instance_id}")
    print(f"State:       {state}")
    print(f"Private IP:  {private_ip}")
    print(f"SSH key SSM: {ssm_path}")
    print()
    if state == "running":
        print("Connect via SSM:  just devbox-ssm")
        print("Stop to save $:   just devbox-stop")
    elif state == "stopped":
        print("Start:  just devbox-start")
    else:
        print(f"Instance is {state} — wait for state to settle.")


def cmd_start():
    outputs = get_stack_outputs()
    instance_id = outputs.get("InstanceId")
    ec2 = boto3.client("ec2", region_name=REGION)

    state = get_instance_state(ec2, instance_id)
    if state == "running":
        print(f"Dev box {instance_id} is already running.")
        cmd_status()
        return

    print(f"Starting dev box {instance_id}...")
    ec2.start_instances(InstanceIds=[instance_id])

    print("Waiting for instance to be running...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])

    # Refresh private IP after start (may change if Elastic IP not assigned)
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    instance = resp["Reservations"][0]["Instances"][0]
    private_ip = instance.get("PrivateIpAddress", "unknown")

    print(f"Dev box running.  Private IP: {private_ip}")
    print()
    print("Connect:  just devbox-ssm")


def cmd_stop():
    outputs = get_stack_outputs()
    instance_id = outputs.get("InstanceId")
    ec2 = boto3.client("ec2", region_name=REGION)

    state = get_instance_state(ec2, instance_id)
    if state == "stopped":
        print(f"Dev box {instance_id} is already stopped.")
        return

    print(f"Stopping dev box {instance_id}...")
    ec2.stop_instances(InstanceIds=[instance_id])

    print("Waiting for instance to stop...")
    waiter = ec2.get_waiter("instance_stopped")
    waiter.wait(InstanceIds=[instance_id])

    print(f"Dev box stopped. Start again with: just devbox-start")


def cmd_ssm():
    outputs = get_stack_outputs()
    instance_id = outputs.get("InstanceId")
    ec2 = boto3.client("ec2", region_name=REGION)

    state = get_instance_state(ec2, instance_id)
    if state != "running":
        print(f"Dev box is {state}. Start it first: just devbox-start")
        sys.exit(1)

    print(f"Opening SSM session to {instance_id}...")
    print("(Type 'exit' to close the session)\n")
    result = subprocess.run(
        ["aws", "ssm", "start-session", "--target", instance_id, "--region", REGION]
    )
    sys.exit(result.returncode)


COMMANDS = {
    "status": cmd_status,
    "start": cmd_start,
    "stop": cmd_stop,
    "ssm": cmd_ssm,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python scripts/devbox.py [{' | '.join(COMMANDS)}]")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
