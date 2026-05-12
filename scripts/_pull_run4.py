"""Pull run 4's response.json off the devbox + check 502 bodies."""
import boto3, time, base64, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ssm = boto3.client("ssm", region_name="us-east-1")
inst = "i-0390c06d166d18926"

cmds = [
    "echo === RUN 4 SIZE ===",
    "wc -c /tmp/q4_probe_04.json",
    "echo === RUN 4 META ===",
    "jq '{session_id, model, tools_called, cost_usd, response_time_ms}' /tmp/q4_probe_04.json",
    "echo === RUN 4 RESPONSE TAIL (last 1500 chars) ===",
    "jq -r .response /tmp/q4_probe_04.json | tail -c 1500",
    "echo === RUN 3 BODY (502) ===",
    "cat /tmp/q4_probe_03.json",
    "echo === RUN 5 BODY (502) ===",
    "cat /tmp/q4_probe_05.json",
]
cmd = ssm.send_command(InstanceIds=[inst], DocumentName="AWS-RunShellScript",
    Parameters={"commands":cmds, "executionTimeout":["60"]})
cid = cmd["Command"]["CommandId"]
for _ in range(20):
    time.sleep(3)
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=inst)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"): break
print("STATUS:", r["Status"])
print(r.get("StandardOutputContent",""))
