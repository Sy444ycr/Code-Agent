from __future__ import annotations

import hashlib
import re

from code_agent.core.models import FeedbackSignal, FeedbackStatus, ToolResult


class FeedbackAdapter:
    def from_tool_result(self, result: ToolResult) -> FeedbackSignal:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        evidence = [line for line in output.splitlines() if line][:5]
        if result.exit_code == 0:
            return FeedbackSignal(
                source=result.tool,
                status=FeedbackStatus.PASSED,
                summary="passed",
                evidence=evidence,
            )
        match = re.search(r"FAILED ([^ ]+) -", output)
        if match:
            fingerprint = f"pytest:{match.group(1)}"
            summary = f"pytest failure: {match.group(1)}"
        else:
            ts = re.search(r"(.+\.tsx?\(\d+,\d+\)): error TS(\d+)", output)
            go = re.search(r"--- FAIL: ([^( ]+)", output)
            maven = re.search(r"Tests run: .* Failures: ([1-9]\d*)", output)
            if ts:
                fingerprint, summary = f"typescript:{ts.group(1)}:TS{ts.group(2)}", ts.group(0)
            elif go:
                fingerprint, summary = f"go:{go.group(1)}", go.group(0)
            elif maven:
                fingerprint, summary = f"maven:failures:{maven.group(1)}", maven.group(0)
            else:
                digest = hashlib.sha1((result.stderr or result.stdout).encode()).hexdigest()[:12]
                fingerprint, summary = (
                    f"{result.tool}:{result.exit_code}:{digest}",
                    output.splitlines()[0] if output else "failed",
                )
        return FeedbackSignal(
            source=result.tool,
            status=FeedbackStatus.FAILED,
            summary=summary,
            evidence=evidence,
            fingerprint=fingerprint,
        )
