"""Validation Agent for DocuPilot AI.

Reuses existing verifier.py, ts_runner.py, and ts_validator.cjs to run genuine
syntax checks, compare executable AST fingerprints between original and proposed
code, detect unwanted logic mutations, and report truthful verification evidence.
"""

import time
from typing import Any, Optional
from pydantic import BaseModel, Field

from ..verifier import verify


class ValidationResult(BaseModel):
    agent_name: str = "Validation Agent"
    status: str = "passed"  # "passed", "failed", "partially_verified"
    passed: bool = True
    global_status: str = "verified"  # "verified", "partially_verified", "failed"
    checks: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    summary: str = ""
    verification: dict[str, Any] = Field(default_factory=dict)
    fingerprint: Optional[dict[str, Any]] = None
    execution_time_ms: float = 0.0
    evidence: dict[str, Any] = Field(default_factory=dict)


class ValidationAgent:
    """Specialist Agent responsible for deterministic syntax and structural integrity verification."""

    def __init__(self):
        self.name = "Validation Agent"

    def run(
        self,
        proposed_code: str,
        language: str,
        original_code: Optional[str] = None,
        doc_style: str = "google",
    ) -> ValidationResult:
        start_time = time.perf_counter()
        lang_clean = language.lower().strip()
        doc_style_clean = (doc_style or "google").lower().strip()

        # Run full modular verification pipeline from verifier.py
        raw_verification = verify(
            proposed_code=proposed_code,
            language=lang_clean,
            original_code=original_code,
            doc_style=doc_style_clean,
        )

        passed = raw_verification.get("passed", False)
        global_status = raw_verification.get("global_status", "failed")
        checks = raw_verification.get("checks", [])
        fingerprint = raw_verification.get("fingerprint")

        errors: list[str] = []
        for c in checks:
            if c.get("status") == "failed":
                errors.append(f"{c.get('name')}: {c.get('details')}")

        status = "failed" if not passed else ("verified" if global_status == "verified" else "partially_verified")

        if not passed:
            summary = f"Validation failed: {len(errors)} check(s) did not pass. {'; '.join(errors)}"
        elif global_status == "verified":
            summary = "All syntax, documentation style, and AST structural consistency checks verified."
        else:
            summary = f"Completed with partial verification. Syntax verification is not supported locally for {language}."

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        evidence = {
            "passed": passed,
            "global_status": global_status,
            "checks_count": len(checks),
            "checks_summary": [{c.get("name"): c.get("status")} for c in checks],
            "fingerprint": fingerprint,
            "note": raw_verification.get("note"),
        }

        return ValidationResult(
            agent_name=self.name,
            status=status,
            passed=passed,
            global_status=global_status,
            checks=checks,
            errors=errors,
            summary=summary,
            verification=raw_verification,
            fingerprint=fingerprint,
            execution_time_ms=duration_ms,
            evidence=evidence,
        )
