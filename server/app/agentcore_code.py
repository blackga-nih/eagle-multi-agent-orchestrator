"""
AgentCore Code Interpreter Service — wraps CodeInterpreter
for managed Python/JS/TS execution sandbox.

Falls back to a restricted local exec when AgentCore is unavailable.
"""

import logging
import os
from typing import Any

logger = logging.getLogger("eagle.agentcore_code")

_REGION = os.getenv("AWS_REGION", "us-east-1")

# Lazy singleton
_code_client = None


def _get_code_client():
    """Lazy-init AgentCore CodeInterpreter."""
    global _code_client
    if _code_client is not None:
        return _code_client

    try:
        from bedrock_agentcore.tools import CodeInterpreter
        _code_client = CodeInterpreter(region=_REGION)
        logger.info("AgentCore CodeInterpreter initialized (region=%s)", _REGION)
        return _code_client
    except Exception as exc:
        logger.warning("AgentCore CodeInterpreter unavailable: %s — using restricted fallback", exc)
        return None


def execute_code(
    code: str,
    language: str = "python",
    packages: list[str] | None = None,
) -> dict[str, Any]:
    """Execute code in a managed sandbox.

    Args:
        code: Code to execute
        language: "python" | "javascript" | "typescript"
        packages: Optional packages to install before execution
    """
    if not code.strip():
        return {"error": "No code provided"}

    client = _get_code_client()

    if client:
        return _agentcore_exec(client, code, language, packages)
    return _fallback_exec(code, language)


def _agentcore_exec(client, code: str, language: str, packages: list[str] | None) -> dict:
    """Execute code via AgentCore CodeInterpreter."""
    try:
        from bedrock_agentcore.tools import code_session

        with code_session(_REGION) as session:
            # Install packages if requested
            if packages:
                install_result = session.install_packages(packages)
                logger.info("Installed packages: %s", packages)

            result = session.execute_code(code)

            # Extract output from result
            output = ""
            error = ""
            if isinstance(result, dict):
                output = result.get("output", result.get("stdout", ""))
                error = result.get("error", result.get("stderr", ""))
            else:
                output = str(result)

            return {
                "language": language,
                "output": output,
                "error": error if error else None,
                "status": "error" if error else "ok",
            }

    except Exception as exc:
        logger.error("AgentCore code execution failed: %s", exc)
        return {"error": f"Code execution failed: {str(exc)}", "language": language, "status": "error"}


def _fallback_exec(code: str, language: str) -> dict:
    """Restricted fallback: only Python, only safe builtins, no I/O."""
    if language != "python":
        return {
            "error": f"Fallback mode only supports Python (AgentCore unavailable for {language})",
            "language": language,
            "status": "error",
        }

    # Restricted execution — no file I/O, no imports of dangerous modules
    _BLOCKED_IMPORTS = {"os", "sys", "subprocess", "shutil", "socket", "http", "urllib", "ctypes", "importlib"}

    for blocked in _BLOCKED_IMPORTS:
        if f"import {blocked}" in code or f"from {blocked}" in code:
            return {
                "error": f"Import '{blocked}' is not allowed in fallback mode. Use AgentCore for full execution.",
                "language": language,
                "status": "error",
            }

    safe_globals = {"__builtins__": {
        "print": print, "len": len, "range": range, "enumerate": enumerate,
        "zip": zip, "map": map, "filter": filter, "sorted": sorted,
        "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
        "int": int, "float": float, "str": str, "bool": bool,
        "list": list, "dict": dict, "set": set, "tuple": tuple,
        "isinstance": isinstance, "type": type, "hasattr": hasattr,
        "getattr": getattr, "setattr": setattr,
    }}

    import io
    import contextlib
    stdout = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout):
            exec(code, safe_globals)
        output = stdout.getvalue()
        return {"language": "python", "output": output, "error": None, "status": "ok", "mode": "fallback"}
    except Exception as exc:
        return {"language": "python", "output": stdout.getvalue(), "error": str(exc), "status": "error", "mode": "fallback"}
