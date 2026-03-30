#!/bin/bash
cd /home/ec2-user/sm_eagle
git fetch origin dev-greg-20260324
git checkout dev-greg-20260324
git reset --hard origin/dev-greg-20260324
echo "=== GIT LOG ==="
git log --oneline -3
echo "=== ALB CHECK ==="
curl -s -o /dev/null -w "%{http_code}" http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com/
echo ""
echo "=== RUNNING E2E JUDGE ==="
cd server
/usr/bin/python3.12 -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys documents \
  --purge-cache \
  --auth-email blackga@nih.gov \
  --auth-password 'Eagle2026!' \
  2>&1 | grep -v "^2026.*DEBUG"
