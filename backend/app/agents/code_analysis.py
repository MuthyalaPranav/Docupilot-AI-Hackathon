"""Code Analysis Agent for DocuPilot AI.

Reuses existing analyzer.py and languages.py modules to perform AST and
heuristic parsing, extract symbols, identify missing documentation, and verify
syntax without modifying the original source code.
"""

import time
from typing import Any, Optional
from pydantic import BaseModel, Field

from ..analyzer import analyze
from ..languages import get_language, SUPPORTED_LANGUAGES


class CodeAnalysisResult(BaseModel):
    agent_name: str = "Code Analysis Agent"
    status: str = "completed"
    language: str
    valid_syntax: Optional[bool] = None
    syntax_status: str
    parser_used: str
    symbol_count: int = 0
    symbols: list[dict[str, Any]] = Field(default_factory=list)
    missing_docs: list[dict[str, Any]] = Field(default_factory=list)
    analysis: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    errors: list[str] = Field(default_factory=list)
    execution_time_ms: float = 0.0
    evidence: dict[str, Any] = Field(default_factory=dict)


class CodeAnalysisAgent:
    """Specialist Agent responsible for structural and syntax analysis of code."""

    def __init__(self):
        self.name = "Code Analysis Agent"

    def run(self, code: str, language: str) -> CodeAnalysisResult:
        start_time = time.perf_counter()
        lang_clean = language.lower().strip()
        cap = get_language(lang_clean)

        if not cap:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return CodeAnalysisResult(
                agent_name=self.name,
                status="failed",
                language=language,
                syntax_status="unsupported_language",
                parser_used="none",
                summary=f"Language '{language}' is not supported.",
                errors=[f"Unsupported language '{language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}"],
                execution_time_ms=duration_ms,
            )

        try:
            raw_analysis = analyze(code, lang_clean)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return CodeAnalysisResult(
                agent_name=self.name,
                status="failed",
                language=lang_clean,
                syntax_status="error",
                parser_used="unknown",
                summary=f"Code parsing failed: {exc}",
                errors=[str(exc)],
                execution_time_ms=duration_ms,
            )

        symbols = raw_analysis.get("symbols", [])
        valid_syntax = raw_analysis.get("valid_syntax")
        syntax_status = raw_analysis.get("syntax_status", "unknown")
        parser_used = raw_analysis.get("parser_used", "regex_heuristic")

        # Identify symbols missing documentation
        missing_docs: list[dict[str, Any]] = []
        for s in symbols:
            s_type = s.get("type", "")
            if s_type in ("FunctionDef", "AsyncFunctionDef", "ClassDef", "Function", "Method", "Class"):
                if not s.get("has_docstring", False):
                    missing_docs.append({
                        "name": s.get("name"),
                        "type": s_type,
                        "line": s.get("line"),
                        "parameters": s.get("parameters", []),
                    })

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if valid_syntax is False:
            status = "failed"
            summary = f"Syntax error detected using {parser_used}: {raw_analysis.get('syntax_message', 'Invalid syntax')}."
        elif valid_syntax is True:
            status = "completed"
            summary = f"Verified syntax via {parser_used}. Found {len(symbols)} symbols ({len(missing_docs)} require documentation)."
        else:
            status = "completed"
            summary = f"Heuristic analysis via {parser_used}. Extracted {len(symbols)} symbols. Syntax not verified locally."

        evidence = {
            "parser_used": parser_used,
            "syntax_message": raw_analysis.get("syntax_message"),
            "fingerprint": raw_analysis.get("fingerprint"),
            "capabilities": raw_analysis.get("capabilities"),
            "missing_docs_count": len(missing_docs),
        }

        return CodeAnalysisResult(
            agent_name=self.name,
            status=status,
            language=lang_clean,
            valid_syntax=valid_syntax,
            syntax_status=syntax_status,
            parser_used=parser_used,
            symbol_count=len(symbols),
            symbols=symbols,
            missing_docs=missing_docs,
            analysis=raw_analysis,
            summary=summary,
            errors=[raw_analysis["syntax_message"]] if valid_syntax is False and raw_analysis.get("syntax_message") else [],
            execution_time_ms=duration_ms,
            evidence=evidence,
        )
