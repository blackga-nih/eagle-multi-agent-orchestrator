"""Read Q5 response file off devbox via SSM, write to local /tmp."""
import boto3, time, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
os.environ.setdefault("AWS_PROFILE", "eagle")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

ssm = boto3.client("ssm", region_name="us-east-1")
inst = "i-0390c06d166d18926"
cmds = [
    "echo SIZE:",
    "wc -c /tmp/q5_resp.json",
    "echo META:",
    'jq "{session_id, model, tools_called, cost_usd, response_time_ms}" /tmp/q5_resp.json',
    "echo TEXT_HEAD:",
    "jq -r .response /tmp/q5_resp.json | head -100",
]
cmd = ssm.send_command(
    InstanceIds=[inst], DocumentName="AWS-RunShellScript",
    Parameters={"commands": cmds, "executionTimeout": ["60"]},
)
cid = cmd["Command"]["CommandId"]
for _ in range(20):
    time.sleep(3)
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=inst)
    if r["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
        break

out = r.get("StandardOutputContent", "") or ""
print("STATUS:", r["Status"])
print(out)
# Also persist to local file for the report writer
with open("/tmp/q5_devbackend_meta.txt", "w", encoding="utf-8") as f:
    f.write(out)
