"""Pull run 4 + 502 bodies, smaller chunks."""
import boto3, time, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ssm = boto3.client("ssm", region_name="us-east-1")
inst = "i-0390c06d166d18926"

# Just run 4
cmd = ssm.send_command(InstanceIds=[inst], DocumentName="AWS-RunShellScript",
    Parameters={"commands":[
        "echo === run 4 sources section ===",
        "jq -r .response /tmp/q4_probe_04.json | grep -E 'eagle-knowledge-base|\\.txt|\\.docx|\\.md' | head -40",
        "echo === run 4 last 600 chars ===",
        "jq -r .response /tmp/q4_probe_04.json | tail -c 600",
    ], "executionTimeout":["30"]})
cid = cmd["Command"]["CommandId"]
for _ in range(15):
    time.sleep(3)
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=inst)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"): break
print("STATUS:", r["Status"])
print(r.get("StandardOutputContent",""))
print("STDERR:", (r.get("StandardErrorContent","") or "")[:500])

# 502 bodies
cmd = ssm.send_command(InstanceIds=[inst], DocumentName="AWS-RunShellScript",
    Parameters={"commands":[
        "echo === run 3 body ===",
        "cat /tmp/q4_probe_03.json | head -c 500",
        "echo",
        "echo === run 5 body ===",
        "cat /tmp/q4_probe_05.json | head -c 500",
    ], "executionTimeout":["30"]})
cid = cmd["Command"]["CommandId"]
for _ in range(15):
    time.sleep(3)
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=inst)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"): break
print("STATUS:", r["Status"])
print(r.get("StandardOutputContent",""))
