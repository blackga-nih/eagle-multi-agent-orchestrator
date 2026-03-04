#!/usr/bin/env python3
"""
devbox_deploy.py — Deploy to EC2 devbox via SSM and manage port tunnels.

Extends devbox.py with remote deployment commands.

Usage:
  python scripts/devbox_deploy.py deploy [--branch main] [--repo origin]
  python scripts/devbox_deploy.py tunnel
  python scripts/devbox_deploy.py health
  python scripts/devbox_deploy.py teardown
  python scripts/devbox_deploy.py logs [backend|frontend]
"""

import json
import subprocess
import sys
import time

import boto3

STACK_NAME = "eagle-ec2-dev"
REGION = "us-east-1"
REPO_DIR = "/home/ec2-user/eagle"
COMPOSE_FILE = "deployment/docker-compose.dev.yml"
REPO_URL = "https://github.com/gblack686/sample-multi-tenant-agent-core-app.git"


def get_instance_id() -> str:
    cf = boto3.client("cloudformation", region_name=REGION)
    try:
        resp = cf.describe_stacks(StackName=STACK_NAME)
        outputs = {o["OutputKey"]: o["OutputValue"] for o in resp["Stacks"][0].get("Outputs", [])}
        return outputs["InstanceId"]
    except Exception as e:
        print(f"Failed to get instance from stack '{STACK_NAME}': {e}")
        print("Is the EC2 stack deployed? Run:")
        print("  aws cloudformation deploy \\")
        print("    --template-file aws/cloud_formation/ec2.yml \\")
        print("    --stack-name eagle-ec2-dev \\")
        print("    --parameter-overrides file://aws/cloud_formation/params/dev/ec2.json \\")
        print("    --capabilities CAPABILITY_NAMED_IAM")
        sys.exit(1)


def ensure_running(instance_id: str):
    ec2 = boto3.client("ec2", region_name=REGION)
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    state = resp["Reservations"][0]["Instances"][0]["State"]["Name"]
    if state == "running":
        print(f"Devbox {instance_id} is running.")
        return
    if state == "stopped":
        print(f"Starting devbox {instance_id}...")
        ec2.start_instances(InstanceIds=[instance_id])
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])
        print("Devbox started. Waiting 15s for SSM agent...")
        time.sleep(15)
    else:
        print(f"Devbox is '{state}' — wait for it to settle, then retry.")
        sys.exit(1)


def ssm_run(instance_id: str, commands: list[str], comment: str = "", timeout: int = 300) -> bool:
    """Run shell commands on the EC2 via SSM send-command. Returns True on success."""
    ssm = boto3.client("ssm", region_name=REGION)
    resp = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands, "executionTimeout": [str(timeout)]},
        Comment=comment[:100] if comment else "devbox-deploy",
        TimeoutSeconds=timeout + 30,
    )
    command_id = resp["Command"]["CommandId"]
    print(f"  SSM command {command_id}: {comment}")

    # Poll for completion
    while True:
        time.sleep(3)
        result = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        status = result["Status"]
        if status in ("Success", "Failed", "Cancelled", "TimedOut"):
            break

    stdout = result.get("StandardOutputContent", "").strip()
    stderr = result.get("StandardErrorContent", "").strip()

    if stdout:
        for line in stdout.split("\n")[-20:]:  # Last 20 lines
            print(f"    {line}")
    if status != "Success":
        print(f"  FAILED ({status})")
        if stderr:
            for line in stderr.split("\n")[-10:]:
                print(f"    ERR: {line}")
        return False

    print(f"  OK")
    return True


def cmd_deploy(branch: str = "main", repo: str = "origin"):
    instance_id = get_instance_id()
    ensure_running(instance_id)

    print()
    print("=== Phase 1: Sync code ===")
    ok = ssm_run(instance_id, [
        f"if [ ! -d {REPO_DIR} ]; then",
        f"  git clone {REPO_URL} {REPO_DIR}",
        f"fi",
        f"cd {REPO_DIR}",
        f"git fetch {repo}",
        f"git checkout {branch}",
        f"git reset --hard {repo}/{branch}",
        f"echo 'On branch:' && git branch --show-current",
        f"echo 'HEAD:' && git log --oneline -1",
    ], comment=f"git sync {repo}/{branch}", timeout=120)
    if not ok:
        sys.exit(1)

    print()
    print("=== Phase 2: Build & start containers ===")
    ok = ssm_run(instance_id, [
        f"cd {REPO_DIR}",
        f"docker compose -f {COMPOSE_FILE} down --remove-orphans 2>/dev/null || true",
        f"docker compose -f {COMPOSE_FILE} up --build --detach",
        f"echo 'Containers:'",
        f"docker compose -f {COMPOSE_FILE} ps --format 'table {{{{.Name}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}'",
    ], comment="docker compose up", timeout=300)
    if not ok:
        sys.exit(1)

    print()
    print("=== Phase 3: Health check ===")
    ok = ssm_run(instance_id, [
        "echo 'Waiting for backend...'",
        "for i in $(seq 1 30); do",
        "  if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then",
        "    echo 'Backend healthy'",
        "    break",
        "  fi",
        "  sleep 2",
        "done",
        "curl -sf http://localhost:8000/api/health || echo 'Backend health check failed'",
        "",
        "echo 'Waiting for frontend...'",
        "for i in $(seq 1 30); do",
        "  STATUS=$(curl -so /dev/null -w '%{http_code}' http://localhost:3000/ 2>/dev/null)",
        "  if [ \"$STATUS\" -ge 200 ] && [ \"$STATUS\" -lt 400 ]; then",
        "    echo \"Frontend healthy (HTTP $STATUS)\"",
        "    break",
        "  fi",
        "  sleep 2",
        "done",
        "curl -so /dev/null -w 'Frontend: HTTP %{http_code}\\n' http://localhost:3000/ || echo 'Frontend health check failed'",
    ], comment="health checks", timeout=120)
    if not ok:
        print("Health checks failed — check logs with: just devbox-logs")
        sys.exit(1)

    print()
    print("=== Deploy complete ===")
    print("Next steps:")
    print("  just devbox-tunnel    # Open port forward (keep running)")
    print("  just devbox-smoke     # Run smoke tests (in another terminal)")


def cmd_tunnel():
    instance_id = get_instance_id()
    ensure_running(instance_id)

    print("Opening SSM port forwards:")
    print("  localhost:3000 → devbox:3000  (frontend)")
    print("  localhost:8000 → devbox:8000  (backend)")
    print()
    print("Keep this running. Ctrl+C to close.")
    print()

    # Start backend tunnel in background
    backend_proc = subprocess.Popen(
        [
            "aws", "ssm", "start-session",
            "--target", instance_id,
            "--region", REGION,
            "--document-name", "AWS-StartPortForwardingSession",
            "--parameters", json.dumps({"portNumber": ["8000"], "localPortNumber": ["8000"]}),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"Backend tunnel PID: {backend_proc.pid}")

    # Frontend tunnel in foreground (blocks)
    try:
        print(f"Starting frontend tunnel (foreground)...")
        subprocess.run(
            [
                "aws", "ssm", "start-session",
                "--target", instance_id,
                "--region", REGION,
                "--document-name", "AWS-StartPortForwardingSession",
                "--parameters", json.dumps({"portNumber": ["3000"], "localPortNumber": ["3000"]}),
            ],
        )
    except KeyboardInterrupt:
        print("\nTunnel closed.")
    finally:
        backend_proc.terminate()
        print("Both tunnels closed.")


def cmd_health():
    instance_id = get_instance_id()
    ensure_running(instance_id)
    ssm_run(instance_id, [
        "echo '=== Docker containers ==='",
        f"cd {REPO_DIR} && docker compose -f {COMPOSE_FILE} ps --format 'table {{{{.Name}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}'",
        "",
        "echo ''",
        "echo '=== Backend health ==='",
        "curl -sf http://localhost:8000/api/health | python3 -m json.tool 2>/dev/null || echo 'Backend not responding'",
        "",
        "echo ''",
        "echo '=== Frontend ==='",
        "curl -so /dev/null -w 'HTTP %{http_code}\\n' http://localhost:3000/ || echo 'Frontend not responding'",
    ], comment="health status")


def cmd_teardown():
    instance_id = get_instance_id()
    ensure_running(instance_id)

    print("Stopping containers on devbox...")
    ssm_run(instance_id, [
        f"cd {REPO_DIR}",
        f"docker compose -f {COMPOSE_FILE} down --remove-orphans",
        "echo 'Containers stopped.'",
    ], comment="teardown containers")

    print()
    print("Containers stopped. Devbox still running.")
    print("To stop the EC2 instance: just devbox-stop")


def cmd_logs(service: str = "backend"):
    instance_id = get_instance_id()
    ensure_running(instance_id)

    ssm_run(instance_id, [
        f"cd {REPO_DIR}",
        f"docker compose -f {COMPOSE_FILE} logs --tail=50 {service}",
    ], comment=f"logs {service}", timeout=30)


COMMANDS = {
    "deploy": cmd_deploy,
    "tunnel": cmd_tunnel,
    "health": cmd_health,
    "teardown": cmd_teardown,
    "logs": cmd_logs,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python scripts/devbox_deploy.py [{' | '.join(COMMANDS)}]")
        print()
        print("Commands:")
        print("  deploy   [--branch main] [--repo origin]  Sync code + start containers")
        print("  tunnel                                     Open SSM port forwards (3000, 8000)")
        print("  health                                     Check container + endpoint health")
        print("  teardown                                   Stop containers on devbox")
        print("  logs     [backend|frontend]                Tail container logs")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "deploy":
        branch = "main"
        repo = "origin"
        for i, arg in enumerate(sys.argv[2:], 2):
            if arg == "--branch" and i + 1 < len(sys.argv):
                branch = sys.argv[i + 1]
            elif arg == "--repo" and i + 1 < len(sys.argv):
                repo = sys.argv[i + 1]
        cmd_deploy(branch, repo)
    elif cmd == "logs":
        service = sys.argv[2] if len(sys.argv) > 2 else "backend"
        cmd_logs(service)
    else:
        COMMANDS[cmd]()
