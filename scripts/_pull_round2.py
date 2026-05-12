"""Pull all 5 round-2 response bodies, extract cited sources."""
import boto3, time, sys, io, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ssm = boto3.client("ssm", region_name="us-east-1")
inst = "i-0390c06d166d18926"

# For each run, dump the response.json (or http error body) sources
cmds = ["echo === BEGIN ==="]
for i in range(1, 6):
    cmds += [
        f"echo --- RUN {i:02d} ---",
        f"FN=/tmp/q4_probe_{i:02d}.json",
        f"if [ ! -f $FN ]; then echo MISSING; continue; fi",
        f"SIZE=$(wc -c < $FN)",
        f"echo size=$SIZE",
        f"if [ $SIZE -lt 200 ]; then echo BODY:; cat $FN; echo; continue; fi",
        f"jq -r .response $FN 2>/dev/null | grep -E '\\.txt|\\.docx|\\.md' | sort -u | head -25",
        f"echo --- end run {i:02d} ---",
    ]
cmds += ["echo === END ==="]

cmd = ssm.send_command(InstanceIds=[inst], DocumentName="AWS-RunShellScript",
    Parameters={"commands": cmds, "executionTimeout":["120"]})
cid = cmd["Command"]["CommandId"]
for _ in range(40):
    time.sleep(3)
    r = ssm.get_command_invocation(CommandId=cid, InstanceId=inst)
    if r["Status"] in ("Success","Failed","Cancelled","TimedOut"): break
print("STATUS:", r["Status"])
print(r.get("StandardOutputContent",""))
