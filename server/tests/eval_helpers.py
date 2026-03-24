"""
EAGLE Eval Helpers — Infrastructure for the expanded eval suite (Phase 1).

Provides validation helpers that run AFTER agent invocations to confirm
observability, tool dispatch, and state integrity.

Classes:
    LangfuseTraceValidator  — Query Langfuse API to validate trace hierarchy,
                               token usage, environment tags, and session IDs.
    CloudWatchEventValidator — Emit structured test events to CW, then query
                               to confirm they arrived (E2E observability).
    ToolChainValidator       — Assert expected tool call chains from Strands
                               Agent result.metrics.tool_metrics.
    SkillPromptValidator     — Check all skill prompt bodies against the 4K
                               truncation limit in strands_agentic_service.

All classes are designed to be non-fatal: they report warnings/failures
but never raise exceptions that abort the test run.
"""

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("eagle.eval_helpers")

# ---------------------------------------------------------------------------
# Shared env loading
# ---------------------------------------------------------------------------

_ENV_CACHE: Dict[str, str] = {}


def _load_env_file(env_file: str = None) -> Dict[str, str]:
    """Load key=value pairs from a .env file. Cached after first call."""
    global _ENV_CACHE
    if _ENV_CACHE:
        return _ENV_CACHE

    if env_file is None:
        env_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", ".env"
        )

    if not os.path.exists(env_file):
        return _ENV_CACHE

    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            _ENV_CACHE[k.strip()] = v.strip().strip('"').strip("'")

    return _ENV_CACHE


def _run_async(coro):
    """Run an async coroutine from sync context (eval tests are async but
    helpers may be called from sync assertion blocks)."""
    try:
        asyncio.get_running_loop()
        # Already in an event loop — run in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)
    except RuntimeError:
        return asyncio.run(coro)


# ============================================================
# Validation result data structures
# ============================================================

@dataclass
class ValidationResult:
    """Single validation check result."""
    check: str
    passed: bool
    detail: str = ""
    value: Any = None


@dataclass
class TraceValidationReport:
    """Aggregated report from LangfuseTraceValidator."""
    trace_id: str = ""
    trace_url: str = ""
    checks: List[ValidationResult] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    generation_count: int = 0
    span_count: int = 0
    environment: str = ""

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def summary(self) -> str:
        p = sum(1 for c in self.checks if c.passed)
        f = len(self.checks) - p
        return f"{p}/{len(self.checks)} checks passed" + (f" ({f} failed)" if f else "")

    def print_report(self, indent: str = "  "):
        """Print human-readable report to stdout."""
        print(f"{indent}Langfuse Trace: {self.trace_url or self.trace_id or 'N/A'}")
        print(f"{indent}Environment: {self.environment or 'unknown'}")
        tin, tout = self.total_input_tokens, self.total_output_tokens
        print(f"{indent}Tokens: {tin} in / {tout} out")
        gens, spans = self.generation_count, self.span_count
        print(f"{indent}Observations: {gens} generations, {spans} spans")
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            detail = f" — {c.detail}" if c.detail else ""
            print(f"{indent}  [{status}] {c.check}{detail}")


@dataclass
class ToolChainReport:
    """Report from ToolChainValidator."""
    expected_tools: List[str] = field(default_factory=list)
    actual_tools: List[str] = field(default_factory=list)
    checks: List[ValidationResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def print_report(self, indent: str = "  "):
        print(f"{indent}Expected tools: {self.expected_tools}")
        print(f"{indent}Actual tools: {self.actual_tools}")
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            detail = f" — {c.detail}" if c.detail else ""
            print(f"{indent}  [{status}] {c.check}{detail}")


@dataclass
class UCValidationMetrics:
    """Per-UC validation gate metrics (matches plan schema)."""
    test_id: int = 0
    uc: str = ""
    name: str = ""
    mvp: str = "MVP1"
    jira: str = ""
    status: str = "FAIL"
    indicators: Dict[str, bool] = field(default_factory=dict)
    indicators_found: int = 0
    indicators_required: int = 3
    tools_expected: List[str] = field(default_factory=list)
    tools_called: List[str] = field(default_factory=list)
    tools_validated: bool = False
    langfuse_trace_id: str = ""
    langfuse_url: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cloudwatch_event_emitted: bool = False
    agent_prompt_source: str = ""
    model: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "uc": self.uc,
            "name": self.name,
            "mvp": self.mvp,
            "jira": self.jira,
            "status": self.status,
            "indicators": self.indicators,
            "indicators_found": self.indicators_found,
            "indicators_required": self.indicators_required,
            "tools_expected": self.tools_expected,
            "tools_called": self.tools_called,
            "tools_validated": self.tools_validated,
            "langfuse_trace_id": self.langfuse_trace_id,
            "langfuse_url": self.langfuse_url,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "cloudwatch_event_emitted": self.cloudwatch_event_emitted,
            "agent_prompt_source": self.agent_prompt_source,
            "model": self.model,
        }


# ============================================================
# LangfuseTraceValidator
# ============================================================

class LangfuseTraceValidator:
    """Validates Langfuse traces post-test.

    Usage:
        validator = LangfuseTraceValidator()
        report = await validator.validate_trace(trace_id)
        report = await validator.validate_session(session_id)
        report = await validator.validate_recent(minutes=5)
    """

    def __init__(self, env_file: str = None):
        env = _load_env_file(env_file)
        default_host = "https://us.cloud.langfuse.com"
        self._host = env.get(
            "LANGFUSE_HOST",
            os.getenv("LANGFUSE_HOST", default_host),
        )
        self._project_id = env.get(
            "LANGFUSE_PROJECT_ID",
            os.getenv("LANGFUSE_PROJECT_ID", ""),
        )
        pk = env.get(
            "LANGFUSE_PUBLIC_KEY",
            os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        )
        sk = env.get(
            "LANGFUSE_SECRET_KEY",
            os.getenv("LANGFUSE_SECRET_KEY", ""),
        )
        self._auth = ""
        if pk and sk:
            self._auth = "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode()
        self._configured = bool(self._auth)

    @property
    def configured(self) -> bool:
        return self._configured

    def trace_url(self, trace_id: str) -> str:
        if self._project_id:
            return f"{self._host}/project/{self._project_id}/traces/{trace_id}"
        return f"{self._host}/traces/{trace_id}"

    async def _get(self, path: str, params: Dict[str, Any] = None) -> Optional[Dict]:
        if not self._configured:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{self._host}{path}",
                    params=params or {},
                    headers={"Authorization": self._auth},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("Langfuse GET %s failed: %s", path, exc)
            return None

    async def get_trace(self, trace_id: str) -> Optional[Dict]:
        return await self._get(f"/api/public/traces/{trace_id}")

    async def list_traces(
        self,
        *,
        limit: int = 20,
        session_id: str = None,
        from_timestamp: str = None,
        to_timestamp: str = None,
    ) -> List[Dict]:
        params: Dict[str, Any] = {
            "limit": limit, "order": "DESC",
        }
        if session_id:
            params["sessionId"] = session_id
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        result = await self._get("/api/public/traces", params)
        return (result or {}).get("data", [])

    async def list_observations(
        self,
        trace_id: str,
        obs_type: str = None,
        limit: int = 100,
    ) -> List[Dict]:
        params: Dict[str, Any] = {"traceId": trace_id, "limit": limit}
        if obs_type:
            params["type"] = obs_type
        result = await self._get("/api/public/observations", params)
        return (result or {}).get("data", [])

    # -- High-level validators --

    async def validate_trace(
        self,
        trace_id: str,
        *,
        expect_environment: str = None,
        expect_session_id: str = None,
        expect_tools: List[str] = None,
        min_input_tokens: int = 1,
    ) -> TraceValidationReport:
        """Run all validations against a single trace."""
        url = self.trace_url(trace_id)
        report = TraceValidationReport(
            trace_id=trace_id, trace_url=url,
        )

        if not self._configured:
            report.checks.append(ValidationResult(
                check="langfuse_configured",
                passed=False,
                detail="Langfuse credentials not set",
            ))
            return report

        # Fetch trace
        trace = await self.get_trace(trace_id)
        if not trace:
            report.checks.append(ValidationResult(
                check="trace_exists",
                passed=False,
                detail=f"Trace {trace_id} not found",
            ))
            return report

        report.checks.append(ValidationResult(check="trace_exists", passed=True))

        # Environment tag
        metadata = trace.get("metadata") or {}
        attrs = metadata.get("attributes") or metadata
        env_val = (
            attrs.get("eagle.environment")
            or metadata.get("environment")
            or ""
        )
        report.environment = env_val

        if expect_environment:
            report.checks.append(ValidationResult(
                check="environment_tag",
                passed=env_val == expect_environment,
                detail=f"expected={expect_environment}, got={env_val}",
                value=env_val,
            ))

        # Session ID
        trace_session = trace.get("sessionId") or ""
        if expect_session_id:
            report.checks.append(ValidationResult(
                check="session_id_propagated",
                passed=trace_session == expect_session_id,
                detail=f"expected={expect_session_id}, got={trace_session}",
                value=trace_session,
            ))

        # Fetch observations
        observations = await self.list_observations(trace_id)
        report.observations = observations

        generations = [o for o in observations if o.get("type") == "GENERATION"]
        spans = [o for o in observations if o.get("type") == "SPAN"]
        report.generation_count = len(generations)
        report.span_count = len(spans)

        # Token counts from GENERATION observations
        total_in = 0
        total_out = 0
        for gen in generations:
            usage = gen.get("usage") or gen.get("usageDetails") or {}
            total_in += (
                usage.get("input", 0)
                or usage.get("inputTokens", 0)
                or usage.get("promptTokens", 0) or 0
            )
            total_out += (
                usage.get("output", 0)
                or usage.get("outputTokens", 0)
                or usage.get("completionTokens", 0) or 0
            )
        report.total_input_tokens = total_in
        report.total_output_tokens = total_out

        report.checks.append(ValidationResult(
            check="input_tokens_positive",
            passed=total_in >= min_input_tokens,
            detail=f"input_tokens={total_in}",
            value=total_in,
        ))

        report.checks.append(ValidationResult(
            check="input_tokens_within_context",
            passed=total_in < 200_000,
            detail=f"input_tokens={total_in} (limit 200K)",
            value=total_in,
        ))

        # Tool call validation via observations
        if expect_tools:
            obs_tool_names = set()
            for obs in observations:
                obs_name = obs.get("name") or ""
                if obs_name:
                    obs_tool_names.add(obs_name)
                # Also check model output for tool_use blocks
                model_output = obs.get("output") or {}
                if isinstance(model_output, dict):
                    for block in model_output.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            obs_tool_names.add(block.get("name", ""))

            for tool in expect_tools:
                found = tool in obs_tool_names
                report.checks.append(ValidationResult(
                    check=f"tool_in_trace:{tool}",
                    passed=found,
                    detail=f"{'found' if found else 'not found'} in trace observations",
                ))

        # Check for empty subagent responses (no empty SPAN outputs)
        empty_spans = []
        for span in spans:
            output = span.get("output")
            if output is not None and (output == "" or output == {} or output == []):
                empty_spans.append(span.get("name", "unnamed"))
        report.checks.append(ValidationResult(
            check="no_empty_subagent_responses",
            passed=len(empty_spans) == 0,
            detail=(
                f"empty spans: {empty_spans}"
                if empty_spans else "all spans have output"
            ),
        ))

        return report

    async def validate_session(
        self,
        session_id: str,
        **kwargs,
    ) -> TraceValidationReport:
        """Find the latest trace for a session and validate it."""
        traces = await self.list_traces(session_id=session_id, limit=1)
        if not traces:
            report = TraceValidationReport()
            report.checks.append(ValidationResult(
                check="trace_for_session",
                passed=False,
                detail=f"No traces found for session {session_id}",
            ))
            return report
        return await self.validate_trace(
            traces[0]["id"],
            expect_session_id=session_id,
            **kwargs,
        )

    async def validate_recent(
        self,
        minutes: int = 10,
        **kwargs,
    ) -> List[TraceValidationReport]:
        """Validate all traces from the last N minutes."""
        now = datetime.now(timezone.utc)
        from_ts = (now - timedelta(minutes=minutes)).isoformat()
        traces = await self.list_traces(from_timestamp=from_ts, limit=50)
        reports = []
        for t in traces:
            r = await self.validate_trace(t["id"], **kwargs)
            reports.append(r)
        return reports

    async def check_skill_prompt_truncation(self, trace_id: str) -> ValidationResult:
        """Check if any subagent received a truncated skill prompt."""
        observations = await self.list_observations(trace_id)
        truncated = []
        for obs in observations:
            # Check system_prompt in metadata for truncation markers
            metadata = obs.get("metadata") or {}
            sys_prompt = metadata.get("system_prompt") or ""
            if "[... truncated" in sys_prompt:
                truncated.append(obs.get("name", "unnamed"))
            # Also check input for truncation markers
            inp = obs.get("input") or ""
            if isinstance(inp, str) and "[... truncated" in inp:
                truncated.append(obs.get("name", "unnamed"))

        return ValidationResult(
            check="skill_prompt_not_truncated",
            passed=len(truncated) == 0,
            detail=(
                f"truncated skills: {truncated}"
                if truncated else "no truncation detected"
            ),
        )


# ============================================================
# CloudWatchEventValidator
# ============================================================

class CloudWatchEventValidator:
    """Emit and query CloudWatch events for E2E observability validation.

    Usage:
        validator = CloudWatchEventValidator()
        validator.emit_test_event(test_id=43, status="pass", tools_used=["search_far"])
        found = validator.query_test_event(test_id=43, run_timestamp=ts)
    """

    LOG_GROUP = "/eagle/test-runs"

    def __init__(self, region: str = None):
        self._region = region or os.environ.get("AWS_REGION", "us-east-1")
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("logs", region_name=self._region)
        return self._client

    @property
    def configured(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False

    def _ensure_log_group(self):
        client = self._get_client()
        try:
            client.create_log_group(logGroupName=self.LOG_GROUP)
        except client.exceptions.ResourceAlreadyExistsException:
            pass

    def emit_test_event(
        self,
        test_id: int,
        test_name: str,
        status: str,
        run_timestamp: str,
        model: str = "",
        tools_used: List[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        session_id: str = "",
        langfuse_trace_id: str = "",
        extra: Dict[str, Any] = None,
    ) -> bool:
        """Emit a structured test_result event to CloudWatch."""
        try:
            self._ensure_log_group()
            client = self._get_client()

            stream_name = f"eval-{run_timestamp.replace(':', '-').replace('+', 'Z')}"
            try:
                client.create_log_stream(
                    logGroupName=self.LOG_GROUP,
                    logStreamName=stream_name,
                )
            except client.exceptions.ResourceAlreadyExistsException:
                pass

            event = {
                "type": "test_result",
                "test_id": test_id,
                "test_name": test_name,
                "status": status,
                "run_timestamp": run_timestamp,
                "model": model,
                "tools_used": tools_used or [],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost_usd, 6),
                "latency_ms": latency_ms,
            }
            if session_id:
                event["session_id"] = session_id
            if langfuse_trace_id:
                event["langfuse_trace_id"] = langfuse_trace_id
            if extra:
                event.update(extra)

            client.put_log_events(
                logGroupName=self.LOG_GROUP,
                logStreamName=stream_name,
                logEvents=[{
                    "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "message": json.dumps(event),
                }],
            )
            return True
        except Exception as exc:
            logger.warning("CloudWatch emit failed: %s", exc)
            return False

    def query_test_event(
        self,
        test_id: int,
        run_timestamp: str = None,
        lookback_minutes: int = 30,
    ) -> Optional[Dict]:
        """Query CloudWatch Logs Insights for a specific test event."""
        try:
            client = self._get_client()
            now = datetime.now(timezone.utc)
            start_time = now - timedelta(minutes=lookback_minutes)

            # CW Logs Insights query
            tid_filter = f'"test_id":{test_id}'
            tid_filter2 = f'"test_id": {test_id}'
            query = (
                "fields @timestamp, @message"
                f" | filter @message like '{tid_filter}'"
                f" or @message like '{tid_filter2}'"
                " | sort @timestamp desc | limit 1"
            )

            response = client.start_query(
                logGroupName=self.LOG_GROUP,
                startTime=int(start_time.timestamp()),
                endTime=int(now.timestamp()),
                queryString=query,
            )
            query_id = response["queryId"]

            # Poll for results (max 10s)
            for _ in range(20):
                time.sleep(0.5)
                result = client.get_query_results(queryId=query_id)
                if result["status"] == "Complete":
                    if result["results"]:
                        for field_list in result["results"]:
                            for f in field_list:
                                if f["field"] == "@message":
                                    return json.loads(f["value"])
                    return None
                if result["status"] in ("Failed", "Cancelled"):
                    return None

            return None
        except Exception as exc:
            logger.warning("CloudWatch query failed: %s", exc)
            return None

    def validate_event_schema(self, event: Dict) -> ValidationResult:
        """Validate that a CW event has the expected schema."""
        required_fields = ["type", "test_id", "test_name", "status", "run_timestamp"]
        missing = [f for f in required_fields if f not in event]
        return ValidationResult(
            check="event_schema_valid",
            passed=len(missing) == 0,
            detail=(
                f"missing fields: {missing}"
                if missing else "all required fields present"
            ),
        )

    def validate_timing_data(self, event: Dict) -> ValidationResult:
        """Validate that timing data (latency_ms) is present and non-zero."""
        latency = event.get("latency_ms", 0)
        return ValidationResult(
            check="timing_data_present",
            passed=latency > 0,
            detail=f"latency_ms={latency}",
            value=latency,
        )


# ============================================================
# ToolChainValidator
# ============================================================

class ToolChainValidator:
    """Validates tool call chains from Strands Agent results.

    Works with StrandsResultCollector.tool_use_blocks or direct
    result.metrics.tool_metrics data.

    Usage:
        validator = ToolChainValidator()
        report = validator.validate(
            tool_use_blocks=[{"tool": "search_far", ...}],
            expected_tools=["search_far"],
        )
        # Or from Strands result directly:
        report = validator.validate_from_result(result, expected_tools=["search_far"])
    """

    def validate(
        self,
        tool_use_blocks: List[Dict],
        expected_tools: List[str],
        *,
        require_all: bool = True,
        require_order: bool = False,
    ) -> ToolChainReport:
        """Validate tool call chain against expectations.

        Args:
            tool_use_blocks: List of {"tool": name, ...} from StrandsResultCollector
            expected_tools: Tool names that should have been called
            require_all: If True, ALL expected tools must appear (default True)
            require_order: If True, expected tools must appear in order
        """
        actual_names = [b.get("tool", "") for b in tool_use_blocks]
        actual_set = set(actual_names)

        report = ToolChainReport(
            expected_tools=expected_tools,
            actual_tools=actual_names,
        )

        # Check each expected tool was called
        for tool in expected_tools:
            found = tool in actual_set
            report.checks.append(ValidationResult(
                check=f"tool_called:{tool}",
                passed=found,
                detail=f"{'found' if found else 'not found'} in {actual_names}",
            ))

        # All expected tools present
        if require_all:
            all_found = all(t in actual_set for t in expected_tools)
            report.checks.append(ValidationResult(
                check="all_expected_tools_called",
                passed=all_found,
                detail=f"expected={expected_tools}, actual={actual_names}",
            ))

        # Order check
        if require_order and len(expected_tools) > 1:
            last_idx = -1
            in_order = True
            for tool in expected_tools:
                try:
                    idx = actual_names.index(tool)
                    if idx <= last_idx:
                        in_order = False
                        break
                    last_idx = idx
                except ValueError:
                    in_order = False
                    break
            report.checks.append(ValidationResult(
                check="tools_in_expected_order",
                passed=in_order,
                detail=f"expected order: {expected_tools}",
            ))

        # At least one tool called (supervisor should always delegate)
        report.checks.append(ValidationResult(
            check="at_least_one_tool_called",
            passed=len(actual_names) > 0,
            detail=f"total tools called: {len(actual_names)}",
        ))

        return report

    def validate_from_result(
        self,
        result,
        expected_tools: List[str],
        agent=None,
        **kwargs,
    ) -> ToolChainReport:
        """Validate tool chain directly from a Strands Agent result.

        Extracts tool names from result.metrics.tool_metrics or agent.messages.
        """
        tool_use_blocks = []

        # Primary: result.metrics.tool_metrics
        try:
            metrics = getattr(result, "metrics", None)
            if metrics and hasattr(metrics, "tool_metrics"):
                for tool_name, tm in metrics.tool_metrics.items():
                    tool_info = getattr(tm, "tool", {}) or {}
                    tool_use_blocks.append({
                        "tool": tool_name,
                        "call_count": getattr(tm, "call_count", 1),
                        "id": tool_info.get("toolUseId", ""),
                    })
        except Exception:
            pass

        # Fallback: agent.messages
        if not tool_use_blocks and agent is not None:
            try:
                for msg in getattr(agent, "messages", []) or []:
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        for block in msg.get("content", []):
                            if isinstance(block, dict) and "toolUse" in block:
                                tu = block["toolUse"]
                                tool_use_blocks.append({
                                    "tool": tu.get("name", ""),
                                    "id": tu.get("toolUseId", ""),
                                })
            except Exception:
                pass

        return self.validate(tool_use_blocks, expected_tools, **kwargs)


# ============================================================
# SkillPromptValidator
# ============================================================

class SkillPromptValidator:
    """Check skill prompt sizes against the 4K truncation limit.

    Reads SKILL_CONSTANTS and PLUGIN_CONTENTS to validate that prompts
    fit within the MAX_SKILL_PROMPT_CHARS budget.
    """

    MAX_CHARS = 4000  # strands_agentic_service.MAX_SKILL_PROMPT_CHARS

    def _size_detail(self, size: int) -> str:
        if size <= self.MAX_CHARS:
            return f"{size} chars"
        over = size - self.MAX_CHARS
        return f"{size} chars — EXCEEDS by {over}"

    def validate_all_skills(self) -> List[ValidationResult]:
        """Check all bundled skill prompts against the limit."""
        results = []
        try:
            from eagle_skill_constants import (
                SKILL_CONSTANTS, PLUGIN_CONTENTS,
            )

            for name, content in SKILL_CONSTANTS.items():
                sz = len(content) if isinstance(content, str) else 0
                results.append(ValidationResult(
                    check=f"skill_within_4k:{name}",
                    passed=sz <= self.MAX_CHARS,
                    detail=self._size_detail(sz),
                    value=sz,
                ))

            for name, entry in PLUGIN_CONTENTS.items():
                body = entry.get("body", "") if isinstance(entry, dict) else ""
                sz = len(body)
                results.append(ValidationResult(
                    check=f"plugin_within_4k:{name}",
                    passed=sz <= self.MAX_CHARS,
                    detail=self._size_detail(sz),
                    value=sz,
                ))

        except ImportError:
            results.append(ValidationResult(
                check="skill_constants_import",
                passed=False,
                detail="eagle_skill_constants not importable",
            ))

        return results

    def validate_skill(self, skill_name: str) -> ValidationResult:
        """Check a single skill prompt size."""
        try:
            from eagle_skill_constants import SKILL_CONSTANTS
            content = SKILL_CONSTANTS.get(skill_name, "")
            sz = len(content) if isinstance(content, str) else 0
            return ValidationResult(
                check=f"skill_within_4k:{skill_name}",
                passed=sz <= self.MAX_CHARS,
                detail=self._size_detail(sz),
                value=sz,
            )
        except ImportError:
            return ValidationResult(
                check=f"skill_within_4k:{skill_name}",
                passed=False,
                detail="eagle_skill_constants not importable",
            )


# ============================================================
# Indicator checker (reusable across UC tests)
# ============================================================

def check_indicators(
    text: str,
    indicators: Dict[str, List[str]],
    required_count: int = 3,
) -> Tuple[Dict[str, bool], int]:
    """Check for presence of indicator keywords in response text.

    Args:
        text: Response text to search (will be lowercased)
        indicators: Dict of {indicator_name: [keyword_variants]}
        required_count: Minimum number of indicators that must match

    Returns:
        (indicator_results, found_count) tuple
    """
    text_lower = text.lower()
    results = {}
    found = 0
    for name, keywords in indicators.items():
        match = any(kw.lower() in text_lower for kw in keywords)
        results[name] = match
        if match:
            found += 1
    return results, found


# ============================================================
# Timer context manager for latency measurement
# ============================================================

class Timer:
    """Simple timer for measuring test latency.

    Usage:
        with Timer() as t:
            result = agent("query")
        print(f"Took {t.elapsed_ms}ms")
    """

    def __init__(self):
        self.start_time = 0.0
        self.end_time = 0.0

    def __enter__(self):
        self.start_time = time.monotonic()
        return self

    def __exit__(self, *args):
        self.end_time = time.monotonic()

    @property
    def elapsed_ms(self) -> int:
        return int((self.end_time - self.start_time) * 1000)

    @property
    def elapsed_s(self) -> float:
        return round(self.end_time - self.start_time, 2)
