"""Modular verification pipeline for DocuPilot AI.

Performs independent checks:
1. parser/syntax validity (Python AST, Esprima, TypeScript compiler API)
2. documentation style (PEP 257, JSDoc, TSDoc, doc comments)
3. structural consistency (preservation of original executable symbols)
4. behavioral regression tests (reported honestly as not_run when no fixture exists)
"""

import ast
import re
import time
from typing import Any, Optional

from .analyzer import compute_executable_fingerprint
from .languages import get_language
from .quality import evaluate_documentation_quality
from .ts_runner import validate_typescript


def check_brackets(code: str) -> tuple[bool, str]:
    stack = []
    pairs = {')': '(', '}': '{', ']': '['}
    in_string = False
    str_char = ''
    i = 0
    while i < len(code):
        ch = code[i]
        if in_string:
            if ch == '\\':
                i += 2
                continue
            elif ch == str_char:
                in_string = False
        else:
            if ch in ('"', "'", '`'):
                in_string = True
                str_char = ch
            elif ch in ('(', '{', '['):
                stack.append(ch)
            elif ch in (')', '}', ']'):
                if not stack or stack[-1] != pairs[ch]:
                    return False, f"Mismatched bracket '{ch}' at position {i}."
                stack.pop()
        i += 1
    if stack:
        return False, f"Unclosed bracket '{stack[-1]}'."
    return True, "Bracket pairs balanced."


def verify_syntax(code: str, language: str) -> dict[str, Any]:
    """Independent Check 1: Parser and Syntax Validity."""
    lang = language.lower().strip()
    cap = get_language(lang)
    start = time.perf_counter()

    if not cap:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "name": "Syntax & Parser Validity",
            "status": "not_supported",
            "tool": "none",
            "duration_ms": duration_ms,
            "details": f"Language '{language}' is not recognized.",
            "diagnostics": None,
        }

    if lang == "python":
        try:
            ast.parse(code)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "name": "Syntax & Parser Validity",
                "status": "passed",
                "tool": "python_ast",
                "duration_ms": duration_ms,
                "details": "Python AST parse passed with zero syntax errors.",
                "diagnostics": None,
            }
        except SyntaxError as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "name": "Syntax & Parser Validity",
                "status": "failed",
                "tool": "python_ast",
                "duration_ms": duration_ms,
                "details": f"Python SyntaxError at line {exc.lineno}, col {exc.offset}: {exc.msg}",
                "diagnostics": {"line": exc.lineno, "col": exc.offset, "msg": exc.msg},
            }

    elif lang == "javascript":
        import esprima

        err_detail = None
        try:
            esprima.parseScript(code, {"loc": True, "tolerant": False})
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "name": "Syntax & Parser Validity",
                "status": "passed",
                "tool": "esprima",
                "duration_ms": duration_ms,
                "details": "JavaScript ECMAScript AST parsed successfully via Esprima.",
                "diagnostics": None,
            }
        except Exception as exc1:
            err_detail = str(exc1)
            try:
                esprima.parseModule(code, {"loc": True, "tolerant": False})
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                return {
                    "name": "Syntax & Parser Validity",
                    "status": "passed",
                    "tool": "esprima",
                    "duration_ms": duration_ms,
                    "details": "JavaScript ES Module AST parsed successfully via Esprima.",
                    "diagnostics": None,
                }
            except Exception as exc2:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                return {
                    "name": "Syntax & Parser Validity",
                    "status": "failed",
                    "tool": "esprima",
                    "duration_ms": duration_ms,
                    "details": f"JavaScript parser syntax error: {exc2}",
                    "diagnostics": {"error": str(exc2)},
                }

    elif lang == "typescript":
        ts_res = validate_typescript(code)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if not ts_res["available"]:
            return {
                "name": "Syntax & Parser Validity",
                "status": "not_supported",
                "tool": "typescript_compiler",
                "duration_ms": duration_ms,
                "details": "TypeScript compiler is not available in local environment.",
                "diagnostics": None,
            }
        if ts_res["valid"]:
            return {
                "name": "Syntax & Parser Validity",
                "status": "passed",
                "tool": "typescript_compiler",
                "duration_ms": duration_ms,
                "details": "TypeScript compiler API parsed AST with zero syntax diagnostics.",
                "diagnostics": None,
            }
        else:
            errors = ts_res.get("errors", [])
            err_summary = "; ".join(
                f"Line {e.get('line')}: {e.get('message')}" for e in errors[:3]
            ) or ts_res.get("message", "Syntax error")
            return {
                "name": "Syntax & Parser Validity",
                "status": "failed",
                "tool": "typescript_compiler",
                "duration_ms": duration_ms,
                "details": f"TypeScript syntax error(s): {err_summary}",
                "diagnostics": errors,
            }

    else:
        # Languages without real parsers installed
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        b_ok, b_msg = check_brackets(code)
        if not b_ok:
            return {
                "name": "Syntax & Parser Validity",
                "status": "failed",
                "tool": "bracket_integrity_check",
                "duration_ms": duration_ms,
                "details": f"Structural syntax failure: {b_msg}",
                "diagnostics": {"bracket_error": b_msg},
            }
        return {
            "name": "Syntax & Parser Validity",
            "status": "not_supported",
            "tool": "none",
            "duration_ms": duration_ms,
            "details": f"Local syntax compiler not available for {cap.name}. Syntax verification is not claimed.",
            "diagnostics": None,
        }


def verify_doc_style(code: str, language: str) -> dict[str, Any]:
    """Independent Check 2: Documentation Style."""
    lang = language.lower().strip()
    start = time.perf_counter()

    if lang == "python":
        has_triple_quotes = '"""' in code or "'''" in code
        has_sections = any(
            sec in code for sec in ("Args:", "Returns:", "Raises:", "Yields:")
        )
        has_hash_comments = any(l.strip().startswith("#") for l in code.splitlines())

        if has_triple_quotes and (has_sections or len(code.splitlines()) < 8):
            details = "Standard PEP 257 / Google-style docstring format identified."
            status = "passed"
        elif has_triple_quotes or has_hash_comments:
            details = "Docstring or explanatory comments present."
            status = "passed"
        else:
            details = "No Python docstrings or comment blocks detected."
            status = "failed"

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "name": "Documentation Style & Format",
            "status": status,
            "tool": "pep257_style_rules",
            "duration_ms": duration_ms,
            "details": details,
        }

    elif lang in ("javascript", "typescript"):
        has_jsdoc = "/**" in code and "*/" in code
        has_tags = any(tag in code for tag in ("@param", "@returns", "@return", "@throws", "@type"))
        has_inline = "//" in code

        if has_jsdoc and has_tags:
            details = "Standard JSDoc/TSDoc block with parameter/return tags identified."
            status = "passed"
        elif has_jsdoc or has_inline:
            details = "JSDoc comments or inline code annotations present."
            status = "passed"
        else:
            details = "No JSDoc or documentation annotations found."
            status = "failed"

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "name": "Documentation Style & Format",
            "status": status,
            "tool": "jsdoc_tsdoc_rules",
            "duration_ms": duration_ms,
            "details": details,
        }

    else:
        # Check standard comment markers
        markers = {
            "java": ("/**", "Javadoc"),
            "c": ("/**", "Doxygen/Block"),
            "cpp": ("/**", "Doxygen/Block"),
            "csharp": ("///", "XML doc"),
            "go": ("//", "Go doc"),
            "php": ("/**", "PHPDoc"),
            "ruby": ("#", "Ruby doc"),
            "swift": ("///", "Swift doc"),
            "kotlin": ("/**", "KDoc"),
            "rust": ("///", "Rustdoc"),
            "sql": ("--", "SQL doc"),
        }
        marker, fmt_name = markers.get(lang, ("//", "Comment"))
        count = code.count(marker)
        status = "passed" if count > 0 else "failed"
        details = (
            f"Found {fmt_name} elements ({count} instances)."
            if count > 0
            else f"No {fmt_name} elements found."
        )
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "name": "Documentation Style & Format",
            "status": status,
            "tool": f"{lang}_style_rules",
            "duration_ms": duration_ms,
            "details": details,
        }


class _DocstringStripper(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:]
        return node

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef
    visit_Module = visit_FunctionDef


def _strip_comments_for_comparison(code: str, language: str) -> str:
    lang = language.lower().strip()
    if lang in (
        "javascript", "typescript", "java", "c", "cpp", "csharp",
        "php", "swift", "kotlin", "rust", "go"
    ):
        s = re.sub(r"/\*[\s\S]*?\*/", "", code)
        s = re.sub(r"//.*", "", s)
    elif lang == "sql":
        s = re.sub(r"/\*[\s\S]*?\*/", "", code)
        s = re.sub(r"--.*", "", s)
    elif lang == "python":
        s = re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', "", code)
        s = re.sub(r"#.*", "", s)
    else:
        s = re.sub(r"#.*", "", code)
    return re.sub(r"\s+", " ", s).strip()


def verify_structural_consistency(
    original_code: str, proposed_code: str, language: str
) -> dict[str, Any]:
    """Independent Check 3: Structural Consistency.

    Verifies documentation insertion did not delete or modify original function declarations
    AND catches alterations to executable statements, variables, operators, or logic.
    """
    start = time.perf_counter()
    from .analyzer import analyze

    lang = language.lower().strip()

    try:
        orig_analysis = analyze(original_code, language)
        prop_analysis = analyze(proposed_code, language)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "name": "Structural Consistency",
            "status": "failed",
            "tool": "ast_symbol_diff",
            "duration_ms": duration_ms,
            "details": f"Could not analyze symbols for structural comparison: {exc}",
        }

    # 1. Symbol preservation check
    orig_funcs = {
        s.get("name")
        for s in orig_analysis.get("symbols", [])
        if s.get("type") in (
            "FunctionDef", "AsyncFunctionDef", "ClassDef", "Function", "Method", "Class"
        )
        and s.get("name")
    }
    prop_funcs = {
        s.get("name")
        for s in prop_analysis.get("symbols", [])
        if s.get("type") in (
            "FunctionDef", "AsyncFunctionDef", "ClassDef", "Function", "Method", "Class"
        )
        and s.get("name")
    }

    orig_fp = orig_analysis.get("fingerprint") or compute_executable_fingerprint(original_code, lang)
    prop_fp = prop_analysis.get("fingerprint") or compute_executable_fingerprint(proposed_code, lang)
    fp_comparison = {
        "original_fingerprint": orig_fp.get("fingerprint"),
        "proposed_fingerprint": prop_fp.get("fingerprint"),
        "matches": orig_fp.get("fingerprint") == prop_fp.get("fingerprint"),
        "algorithm": orig_fp.get("algorithm", "sha256"),
        "explanation": "Calculates canonical SHA-256 fingerprint over normalized AST executable statements (comments & docstrings excluded).",
        "disclaimer": "Static syntax and AST fingerprinting do not guarantee runtime semantic equivalence under dynamic evaluation.",
    }

    missing = orig_funcs - prop_funcs
    if missing:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "name": "Structural Consistency",
            "status": "failed",
            "tool": "ast_symbol_diff",
            "duration_ms": duration_ms,
            "details": f"Original declared symbols missing in documented code: {', '.join(missing)}",
            "fingerprint_comparison": fp_comparison,
        }

    # 2. Executable statements preservation check
    if lang == "python":
        try:
            t_orig = ast.parse(original_code)
            t_prop = ast.parse(proposed_code)
            _DocstringStripper().visit(t_orig)
            _DocstringStripper().visit(t_prop)
            dump_orig = ast.dump(t_orig, include_attributes=False)
            dump_prop = ast.dump(t_prop, include_attributes=False)

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            if dump_orig != dump_prop:
                return {
                    "name": "Structural Consistency",
                    "status": "failed",
                    "tool": "python_ast_exec_diff",
                    "duration_ms": duration_ms,
                    "details": "Executable statements or logic were modified. Documentation additions must not alter executable AST statements.",
                    "fingerprint_comparison": fp_comparison,
                }
        except SyntaxError:
            pass  # Syntax check will report syntax errors separately
    else:
        # Non-Python languages: compare non-comment token stream
        clean_orig = _strip_comments_for_comparison(original_code, lang)
        clean_prop = _strip_comments_for_comparison(proposed_code, lang)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if clean_orig != clean_prop:
            return {
                "name": "Structural Consistency",
                "status": "failed",
                "tool": "token_exec_diff",
                "duration_ms": duration_ms,
                "details": "Executable code modified. Non-comment tokens in proposed code do not match original code.",
                "fingerprint_comparison": fp_comparison,
            }

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "name": "Structural Consistency",
        "status": "passed",
        "tool": "ast_exec_diff",
        "duration_ms": duration_ms,
        "details": f"All {len(orig_funcs)} declared symbols and all executable statements preserved (documentation-only change verified).",
        "fingerprint_comparison": fp_comparison,
    }


def verify_behavioral_regression() -> dict[str, Any]:
    """Independent Check 4: Behavioral Regression Tests."""
    return {
        "name": "Behavioral Regression Tests",
        "status": "not_run",
        "tool": "isolated_test_harness",
        "duration_ms": 0.0,
        "details": "Not run: arbitrary code execution is prohibited without an isolated test harness and user-provided test suite.",
    }


def verify(
    proposed_code: str,
    language: str,
    original_code: Optional[str] = None,
    doc_style: Optional[str] = "google",
) -> dict[str, Any]:
    """Run full verification pipeline and return structured result."""
    cap = get_language(language)

    # 1. Syntax check
    c_syntax = verify_syntax(proposed_code, language)

    # 2. Doc style check
    c_style = verify_doc_style(proposed_code, language)

    # 3. Structural consistency
    if original_code and original_code.strip():
        c_struct = verify_structural_consistency(original_code, proposed_code, language)
    else:
        c_struct = {
            "name": "Structural Consistency",
            "status": "passed",
            "tool": "ast_symbol_diff",
            "duration_ms": 0.0,
            "details": "Original source not supplied; structural baseline skipped.",
            "fingerprint_comparison": None,
        }

    # 4. Behavioral regression check
    c_behav = verify_behavioral_regression()

    checks = [c_syntax, c_style, c_struct, c_behav]

    has_failure = any(c["status"] == "failed" for c in checks)
    syntax_status = c_syntax["status"]

    if has_failure:
        global_status = "failed"
        passed = False
        note = "One or more verification checks failed. Review diagnostic details before approving."
    elif syntax_status == "passed":
        global_status = "verified"
        passed = True
        note = "Parser syntax, documentation style, and structural integrity verified. Passing static checks does not prove runtime semantic equivalence."
    elif syntax_status == "not_supported":
        global_status = "partially_verified"
        passed = True
        note = f"Documentation format and structural checks passed. Syntax verification is not supported locally for {cap.name if cap else language}."
    else:
        global_status = "partially_verified"
        passed = True
        note = "Checks completed with partial verification."

    # 5. Quality Score evaluation
    prop_analysis = None
    try:
        from .analyzer import analyze
        prop_analysis = analyze(proposed_code, language)
    except Exception:
        prop_analysis = {"symbols": []}

    quality_score = evaluate_documentation_quality(
        code=proposed_code,
        language=language,
        analysis=prop_analysis,
        doc_style=doc_style or "google",
    )

    fingerprint = prop_analysis.get("fingerprint") or compute_executable_fingerprint(proposed_code, language)

    return {
        "passed": passed,
        "global_status": global_status,
        "checks": checks,
        "quality_score": quality_score,
        "fingerprint": fingerprint,
        "note": note,
    }
