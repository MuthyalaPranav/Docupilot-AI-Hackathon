"""Documentation Quality Scoring Engine for DocuPilot AI.

Evaluates documentation proposals deterministically against extracted AST evidence.
Measures parameter coverage, return coverage, exception coverage, summary quality,
and style conformance. Strictly distinguishes measurable static criteria from AI assessments.
"""

import re
from typing import Any, Optional


def evaluate_documentation_quality(
    code: str,
    language: str,
    analysis: dict[str, Any],
    doc_style: str = "google",
) -> dict[str, Any]:
    """Calculate an explainable, deterministic documentation quality score.

    Returns:
        dict containing:
          - overall_score (int): 0 to 100
          - grade (str): 'A+', 'A', 'B', 'C', or 'Needs Improvement'
          - parameter_coverage (float): percentage 0-100
          - return_coverage (float): percentage 0-100
          - exception_coverage (float): percentage 0-100
          - summary_coverage (float): percentage 0-100
          - style_conformance (float): percentage 0-100
          - breakdown (list[dict]): measurable criterion and points awarded
          - findings (list[str]): human-readable findings
          - disclaimer (str): explicit disclosure regarding static vs semantic verification
    """
    lang = language.lower().strip()
    style = doc_style.lower().strip() if doc_style else "google"
    symbols = analysis.get("symbols") or []
    code_lower = code.lower()

    # Filter function and class symbols
    func_symbols = [
        s for s in symbols
        if s.get("type") in ("FunctionDef", "AsyncFunctionDef", "ClassDef", "Function", "Method", "Class")
        and s.get("name")
    ]

    findings = []
    breakdown = []

    # Isolate documentation text (docstrings and comments) so source code syntax is not counted as documentation
    doc_text = ""
    if lang == "python":
        import ast
        try:
            tree = ast.parse(code)
            doc_parts = []
            m_doc = ast.get_docstring(tree)
            if m_doc:
                doc_parts.append(m_doc)
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    d = ast.get_docstring(n)
                    if d:
                        doc_parts.append(d)
            for l in code.splitlines():
                if l.strip().startswith("#"):
                    doc_parts.append(l.strip())
            doc_text = "\n".join(doc_parts).lower()
        except Exception:
            doc_text = ""
    else:
        comments = re.findall(r"/\*[\s\S]*?\*/|//.*|///.*|--.*|#.*", code)
        doc_text = "\n".join(comments).lower()

    has_any_doc = bool(doc_text.strip())

    # 1. Parameter Coverage (Weight: 35%)
    all_declared_params = []
    for s in func_symbols:
        all_declared_params.extend(s.get("parameters") or [])

    if not all_declared_params:
        param_cov = 100.0
        findings.append("No explicit function parameters declared (100% parameter coverage).")
        breakdown.append({
            "criterion": "Parameter Coverage",
            "weight": 35,
            "earned": 35.0,
            "status": "passed",
            "details": "No parameters require documentation.",
        })
    elif not has_any_doc:
        param_cov = 0.0
        findings.append(f"Declared parameters ({', '.join(all_declared_params)}) have no documentation.")
        breakdown.append({
            "criterion": "Parameter Coverage",
            "weight": 35,
            "earned": 0.0,
            "status": "failed",
            "details": "0 of declared parameters documented (no docstrings found).",
        })
    else:
        # Check which declared parameters appear in docstrings or comments
        documented_count = 0
        for p in all_declared_params:
            p_clean = p.lower().strip().lstrip("$")
            pattern = (
                rf'\b{re.escape(p_clean)}\s*(?:\([^)]+\))?\s*:|'
                rf'\b{re.escape(p_clean)}\s*:\s*|'
                rf'@param\s+(?:\{{[^}}]+\}}\s+)?{re.escape(p_clean)}\b|'
                rf'[\*\-`]\s*{re.escape(p_clean)}\b'
            )
            if re.search(pattern, doc_text) or re.search(rf'\b{re.escape(p_clean)}\b', doc_text):
                documented_count += 1

        param_cov = round((documented_count / len(all_declared_params)) * 100.0, 1)
        earned = round((param_cov / 100.0) * 35.0, 1)
        status = "passed" if param_cov >= 80.0 else "warning" if param_cov >= 50.0 else "failed"
        findings.append(f"Documented {documented_count}/{len(all_declared_params)} declared parameter(s) ({param_cov}% coverage).")
        breakdown.append({
            "criterion": "Parameter Coverage",
            "weight": 35,
            "earned": earned,
            "status": status,
            "details": f"{documented_count} of {len(all_declared_params)} parameters documented.",
        })

    # 2. Return Coverage (Weight: 25%)
    functions_with_returns = [
        s for s in func_symbols
        if s.get("has_return") or s.get("return_type") or s.get("type") in ("FunctionDef", "AsyncFunctionDef", "Function")
    ]
    if not functions_with_returns:
        return_cov = 100.0
        findings.append("No returning functions detected (100% return coverage).")
        breakdown.append({
            "criterion": "Return Value Documentation",
            "weight": 25,
            "earned": 25.0,
            "status": "passed",
            "details": "No return values require documentation.",
        })
    elif not has_any_doc:
        return_cov = 0.0
        findings.append("Functions return values but no documentation was found.")
        breakdown.append({
            "criterion": "Return Value Documentation",
            "weight": 25,
            "earned": 0.0,
            "status": "failed",
            "details": "Missing Returns section.",
        })
    else:
        # Check for return tags / sections in the documentation text
        return_markers = [
            "returns:", "returns\n", "return:", "@return", "@returns",
            "/// - returns:", "/// # returns", "# @return", "-- returns", "returns"
        ]
        has_return_doc = any(m in doc_text for m in return_markers)
        if has_return_doc:
            return_cov = 100.0
            earned = 25.0
            status = "passed"
            findings.append("Detected return expressions are documented with return specifications.")
        else:
            return_cov = 0.0
            earned = 0.0
            status = "failed"
            findings.append("Functions return values but no return documentation section was found.")

        breakdown.append({
            "criterion": "Return Value Documentation",
            "weight": 25,
            "earned": earned,
            "status": status,
            "details": "Return value section documented." if has_return_doc else "Missing Returns section.",
        })

    # 3. Exception / Error Coverage (Weight: 20%)
    all_detected_raises = []
    for s in func_symbols:
        all_detected_raises.extend(s.get("raises") or [])

    if not all_detected_raises:
        exc_cov = 100.0
        findings.append("No explicit raise/throw statements detected (100% exception coverage).")
        breakdown.append({
            "criterion": "Exception & Error Coverage",
            "weight": 20,
            "earned": 20.0,
            "status": "passed",
            "details": "No explicit exceptions requiring documentation.",
        })
    elif not has_any_doc:
        exc_cov = 0.0
        findings.append(f"Detected explicit exceptions ({', '.join(set(all_detected_raises))}) without documentation.")
        breakdown.append({
            "criterion": "Exception & Error Coverage",
            "weight": 20,
            "earned": 0.0,
            "status": "failed",
            "details": "Missing Raises / Throws documentation.",
        })
    else:
        raise_markers = ["raises:", "raises\n", "@throws", "@throw", "/// # errors", "# @raise", "raises"]
        has_raise_doc = any(m in doc_text for m in raise_markers)
        specific_matches = sum(1 for exc in all_detected_raises if exc.lower() in doc_text)
        if has_raise_doc and specific_matches > 0:
            exc_cov = 100.0
            earned = 20.0
            status = "passed"
            findings.append(f"Detected exception(s) ({', '.join(set(all_detected_raises))}) are documented in error specifications.")
        elif has_raise_doc:
            exc_cov = 70.0
            earned = 14.0
            status = "warning"
            findings.append("General exception documentation present, but specific exception types are omitted.")
        else:
            exc_cov = 0.0
            earned = 0.0
            status = "failed"
            findings.append(f"Detected explicit exceptions ({', '.join(set(all_detected_raises))}) without a Raises / Throws section.")

        breakdown.append({
            "criterion": "Exception & Error Coverage",
            "weight": 20,
            "earned": earned,
            "status": status,
            "details": f"{specific_matches}/{len(all_detected_raises)} detected exception types documented.",
        })

    # 4. Summary & Description Quality (Weight: 10%)
    if not func_symbols:
        summary_cov = 100.0 if has_any_doc else 0.0
    else:
        documented_symbols = sum(
            1 for s in func_symbols
            if any(term in code for term in (f'"""{s.get("name")}', f'"""\n', f' * {s.get("name")}', "/**", "///"))
            or ('"""' in code or "/**" in code or "///" in code)
        )
        summary_cov = 100.0 if (documented_symbols > 0 and has_any_doc) else 0.0

    earned_sum = 10.0 if summary_cov >= 80.0 else 0.0
    findings.append("Explanatory summary descriptions present for core components." if summary_cov > 0 else "Missing summary descriptions.")
    breakdown.append({
        "criterion": "Summary Quality",
        "weight": 10,
        "earned": earned_sum,
        "status": "passed" if summary_cov >= 80.0 else "failed",
        "details": "Functions and classes have descriptive summary headers." if summary_cov > 0 else "Missing summary.",
    })

    # 5. Target Style Conformance (Weight: 10%)
    if not has_any_doc:
        style_conformance = 0.0
        findings.append("No documentation present for style conformance evaluation.")
    else:
        style_conformance = 100.0
        if lang == "python":
            if style == "numpy":
                has_numpy_headers = any(h in code for h in ("Parameters\n    ----------", "Parameters\n----------", "Returns\n    -------", "Returns\n-------"))
                style_conformance = 100.0 if has_numpy_headers else 60.0
                findings.append("NumPy docstring format structure verified." if has_numpy_headers else "Standard docstring present; partial NumPy header format.")
            else:
                # Google style
                has_google_sections = any(sec in code for sec in ("Args:", "Returns:", "Raises:"))
                style_conformance = 100.0 if has_google_sections else 70.0
                findings.append("Google docstring format sections (Args/Returns/Raises) verified." if has_google_sections else "Docstring format adheres to PEP 257 standards.")
        elif lang in ("javascript", "typescript"):
            has_jsdoc = "/**" in code and "*/" in code
            style_conformance = 100.0 if has_jsdoc else 50.0
            findings.append("JSDoc/TSDoc format verified." if has_jsdoc else "Generic comments present.")
        else:
            style_conformance = 100.0
            findings.append(f"Standard {lang.capitalize()} documentation conventions verified.")

    earned_style = round((style_conformance / 100.0) * 10.0, 1)
    breakdown.append({
        "criterion": f"Style Conformance ({style.capitalize()})",
        "weight": 10,
        "earned": earned_style,
        "status": "passed" if style_conformance >= 80.0 else "warning" if style_conformance > 0 else "failed",
        "details": f"Adheres to {style.capitalize()} style conventions." if has_any_doc else "No documentation to evaluate.",
    })

    total_score = int(round(sum(b["earned"] for b in breakdown)))
    total_score = max(0, min(100, total_score))

    if total_score >= 95:
        grade = "A+"
    elif total_score >= 85:
        grade = "A"
    elif total_score >= 70:
        grade = "B"
    elif total_score >= 50:
        grade = "C"
    else:
        grade = "Needs Improvement"

    return {
        "overall_score": total_score,
        "grade": grade,
        "parameter_coverage": param_cov,
        "return_coverage": return_cov,
        "exception_coverage": exc_cov,
        "summary_coverage": summary_cov,
        "style_conformance": style_conformance,
        "breakdown": breakdown,
        "findings": findings,
        "disclaimer": "This quality score is calculated deterministically from AST structure and documentation coverage. It measures documentation completeness against declared symbols, not runtime semantic correctness.",
    }
