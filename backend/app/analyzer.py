"""Code analyzer for DocuPilot AI.

Extracts AST symbols and performs genuine syntax validation for supported languages.
Clearly distinguishes verified AST parsing from heuristic regex symbol extraction.
"""

import ast
import re
from typing import Any, Optional

from .languages import REGISTRY, SUPPORTED_LANGUAGES, get_language
from .ts_runner import validate_typescript


def clean_param_name(p: str, lang: str) -> str:
    p = p.strip().split("=")[0].strip()
    if not p:
        return ""
    if ":" in p:
        # TypeScript, Swift, Kotlin, Rust: name: Type
        p_name = p.split(":")[0].strip()
    elif lang == "go":
        # Go: name Type
        p_name = p.split()[0].strip()
    else:
        # Java, C, C++, C#, PHP: Type name or $name
        p_name = p.split()[-1].lstrip("*&").strip()
    p_name = p_name.lstrip("$").strip()
    if p_name in ("void", "...", "self", "this", "mut"):
        return ""
    return p_name


import hashlib

def _extract_python_function_details(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    param_names = []
    param_details = []
    for a in node.args.args:
        if a.arg in ("self", "cls"):
            continue
        param_names.append(a.arg)
        type_str = None
        if a.annotation:
            try:
                type_str = ast.unparse(a.annotation)
            except Exception:
                type_str = None
        param_details.append({
            "name": a.arg,
            "type": type_str,
        })

    return_type = None
    if node.returns:
        try:
            return_type = ast.unparse(node.returns)
        except Exception:
            return_type = None

    has_return = False
    returns_none_only = True
    is_generator = False
    detected_raises = []

    for item in ast.walk(node):
        if item is node:
            continue
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(item, ast.Return):
            has_return = True
            if item.value is not None and not (isinstance(item.value, ast.Constant) and item.value.value is None):
                returns_none_only = False
        elif isinstance(item, (ast.Yield, ast.YieldFrom)):
            is_generator = True
        elif isinstance(item, ast.Raise):
            if item.exc:
                if isinstance(item.exc, ast.Name):
                    detected_raises.append(item.exc.id)
                elif isinstance(item.exc, ast.Call):
                    if isinstance(item.exc.func, ast.Name):
                        detected_raises.append(item.exc.func.id)
                    elif isinstance(item.exc.func, ast.Attribute):
                        detected_raises.append(item.exc.func.attr)
                elif isinstance(item.exc, ast.Attribute):
                    detected_raises.append(item.exc.attr)

    unique_raises = []
    for r in detected_raises:
        if r not in unique_raises:
            unique_raises.append(r)

    return {
        "parameters": param_names,
        "param_details": param_details,
        "return_type": return_type,
        "has_return": has_return,
        "returns_none_only": returns_none_only if has_return else False,
        "is_generator": is_generator,
        "is_async": isinstance(node, ast.AsyncFunctionDef),
        "raises": unique_raises,
    }


def compute_executable_fingerprint(source: str, language: str) -> dict[str, Any]:
    """Compute a canonical 16-character SHA-256 fingerprint of executable code.

    Strips comments and docstrings to represent executable statements.
    """
    lang = language.lower().strip()
    raw_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    if lang == "python":
        try:
            tree = ast.parse(source)

            class _Stripper(ast.NodeTransformer):
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

            _Stripper().visit(tree)
            canonical = ast.dump(tree, include_attributes=False)
            fp = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
            return {
                "fingerprint": fp,
                "raw_hash": raw_hash,
                "algorithm": "sha256_ast_executable",
                "explanation": "SHA-256 of normalized Python AST executable statements (comments & docstrings excluded).",
                "disclaimer": "Static AST fingerprinting confirms structural statement alignment, but does not prove runtime semantic equivalence.",
            }
        except SyntaxError:
            pass

    if lang in (
        "javascript", "typescript", "java", "c", "cpp", "csharp",
        "php", "swift", "kotlin", "rust", "go"
    ):
        s = re.sub(r"/\*[\s\S]*?\*/", "", source)
        s = re.sub(r"//.*", "", s)
    elif lang == "sql":
        s = re.sub(r"/\*[\s\S]*?\*/", "", source)
        s = re.sub(r"--.*", "", s)
    elif lang == "python":
        s = re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', "", source)
        s = re.sub(r"#.*", "", s)
    else:
        s = re.sub(r"#.*", "", source)

    tokens = re.sub(r"\s+", " ", s).strip()
    fp = hashlib.sha256(tokens.encode("utf-8")).hexdigest()[:16]
    return {
        "fingerprint": fp,
        "raw_hash": raw_hash,
        "algorithm": "sha256_token_stream",
        "explanation": "SHA-256 of non-comment token stream.",
        "disclaimer": "Token fingerprinting verifies non-comment tokens, but does not prove runtime semantic equivalence.",
    }


def analyze_python(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "language": "python",
            "valid_syntax": False,
            "syntax_status": "invalid",
            "parser_used": "python_ast",
            "syntax_message": f"SyntaxError at line {exc.lineno}: {exc.msg}",
            "symbols": [],
        }

    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            sym_data: dict[str, Any] = {
                "type": node.__class__.__name__,
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "has_docstring": ast.get_docstring(node) is not None,
            }
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                details = _extract_python_function_details(node)
                sym_data.update(details)
            else:
                sym_data["parameters"] = []
                sym_data["param_details"] = []
            symbols.append(sym_data)

    if not symbols:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols.append({
                            "type": "Variable",
                            "name": target.id,
                            "line": node.lineno,
                            "end_line": getattr(node, "end_lineno", node.lineno),
                            "parameters": [],
                            "has_docstring": False,
                        })
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                symbols.append({
                    "type": "Variable",
                    "name": node.target.id,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "parameters": [],
                    "has_docstring": False,
                })
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func_name = getattr(node.value.func, "id", None) or getattr(
                    node.value.func, "attr", "call"
                )
                symbols.append({
                    "type": "Call",
                    "name": f"{func_name}()",
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "parameters": [],
                    "has_docstring": False,
                })

    return {
        "language": "python",
        "valid_syntax": True,
        "syntax_status": "verified",
        "parser_used": "python_ast",
        "syntax_message": "Python AST parse passed successfully.",
        "symbols": symbols,
    }


def analyze_javascript(source: str) -> dict[str, Any]:
    import esprima

    tree = None
    parse_error = None
    try:
        tree = esprima.parseScript(source, {"loc": True, "tolerant": False})
    except Exception as exc1:
        parse_error = exc1
        try:
            tree = esprima.parseModule(source, {"loc": True, "tolerant": False})
            parse_error = None
        except Exception as exc2:
            parse_error = exc2

    if tree is None:
        return {
            "language": "javascript",
            "valid_syntax": False,
            "syntax_status": "invalid",
            "parser_used": "esprima",
            "syntax_message": f"JavaScript syntax error: {parse_error}",
            "symbols": [],
        }

    symbols = []

    def walk(node):
        if isinstance(node, dict):
            typ = node.get("type")
            if typ in (
                "FunctionDeclaration",
                "ClassDeclaration",
                "MethodDefinition",
                "ArrowFunctionExpression",
                "FunctionExpression",
            ):
                name = None
                ident = node.get("id")
                if isinstance(ident, dict):
                    name = ident.get("name")
                if not name and isinstance(node.get("key"), dict):
                    name = node["key"].get("name")
                params = []
                for p in node.get("params", []):
                    if isinstance(p, dict):
                        if p.get("type") == "AssignmentPattern" and isinstance(
                            p.get("left"), dict
                        ):
                            params.append(p["left"].get("name") or "param")
                        else:
                            params.append(p.get("name") or p.get("type", "parameter"))
                    elif isinstance(p, str):
                        params.append(p)
                symbols.append({
                    "type": typ,
                    "name": name or "(anonymous)",
                    "line": (node.get("loc") or {}).get("start", {}).get("line"),
                    "parameters": params,
                })
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(tree.toDict())
    return {
        "language": "javascript",
        "valid_syntax": True,
        "syntax_status": "verified",
        "parser_used": "esprima",
        "syntax_message": "JavaScript ECMAScript parse passed successfully.",
        "symbols": symbols,
    }


def analyze_typescript(source: str) -> dict[str, Any]:
    res = validate_typescript(source)
    if not res["available"]:
        heuristic = analyze_regex(source, "typescript")
        heuristic["valid_syntax"] = None
        heuristic["syntax_status"] = "parser_unavailable"
        heuristic["parser_used"] = "regex_heuristic"
        heuristic["syntax_message"] = res.get(
            "message", "TypeScript compiler not available in runtime."
        )
        return heuristic

    if res["valid"] is False:
        return {
            "language": "typescript",
            "valid_syntax": False,
            "syntax_status": "invalid",
            "parser_used": "typescript_compiler",
            "syntax_message": res.get("message", "TypeScript syntax error"),
            "errors": res.get("errors", []),
            "symbols": [],
        }

    return {
        "language": "typescript",
        "valid_syntax": True,
        "syntax_status": "verified",
        "parser_used": "typescript_compiler",
        "syntax_message": "TypeScript compiler AST parse passed successfully.",
        "symbols": res.get("symbols", []),
    }


def analyze_regex(source: str, language: str) -> dict[str, Any]:
    symbols = []
    lines = source.splitlines()
    patterns: list[tuple[str, str]] = []

    if language in ("c", "cpp"):
        patterns.append((
            r"^\s*(?:(?:inline|static|virtual|const|extern|constexpr)\s+)*(?:[\w:*&<>]+\s+)+(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*(?:\{|;)?$",
            "Function",
        ))
        patterns.append(
            (r"^\s*(?:class|struct)\s+(\w+)", "Class" if language == "cpp" else "Struct")
        )
    elif language == "java":
        patterns.append((
            r"^\s*(?:public|protected|private|static|final|abstract|synchronized|\s)*\s+(?:[\w<>\[\],]+\s+)+(\w+)\s*\(([^)]*)\)",
            "Method",
        ))
        patterns.append(
            (r"^\s*(?:public|protected|private|\s)*\s*(?:class|interface|enum|record)\s+(\w+)", "Class")
        )
    elif language == "csharp":
        patterns.append((
            r"^\s*(?:public|protected|private|static|async|virtual|override|abstract|\s)*\s*(?:[\w<>\[\],?]+\s+)+(\w+)\s*\(([^)]*)\)",
            "Method",
        ))
        patterns.append(
            (r"^\s*(?:public|protected|private|\s)*\s*(?:class|interface|struct|record)\s+(\w+)", "Class")
        )
    elif language == "go":
        patterns.append((r"^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)", "Function"))
        patterns.append((r"^\s*type\s+(\w+)\s+(?:struct|interface)", "Type"))
    elif language == "php":
        patterns.append(
            (r"^\s*(?:public|protected|private|static|\s)*\s*function\s+(\w+)\s*\(([^)]*)\)", "Function")
        )
        patterns.append((r"^\s*(?:abstract|final|\s)*\s*class\s+(\w+)", "Class"))
    elif language == "ruby":
        patterns.append((r"^\s*def\s+([A-Za-z0-9_!?]+)(?:\s*\(([^)]*)\))?", "Method"))
        patterns.append((r"^\s*(?:class|module)\s+([A-Za-z0-9_:]+)", "Class"))
    elif language == "swift":
        patterns.append(
            (r"^\s*(?:public|private|fileprivate|internal|open|static|\s)*\s*func\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)", "Function")
        )
        patterns.append((r"^\s*(?:class|struct|protocol|enum)\s+(\w+)", "Type"))
    elif language == "kotlin":
        patterns.append(
            (r"^\s*(?:public|private|protected|internal|override|suspend|\s)*\s*fun\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)", "Function")
        )
        patterns.append((r"^\s*(?:data\s+)?(?:class|interface|object)\s+(\w+)", "Class"))
    elif language == "rust":
        patterns.append(
            (r"^\s*(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)", "Function")
        )
        patterns.append((r"^\s*(?:pub(?:\([^)]+\))?\s+)?(?:struct|enum|trait)\s+(\w+)", "Type"))
    elif language == "sql":
        patterns.append(
            (r"(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+([A-Za-z0-9_]+)", "Procedure")
        )
        patterns.append(
            (r"(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)\s+([A-Za-z0-9_]+)", "Table")
        )
        patterns.append((r"(?i)^\s*(?:SELECT|INSERT|UPDATE|DELETE|WITH)\s+", "Query"))
    else:
        patterns.append((r"^\s*(?:def|func|function|fn)\s+(\w+)\s*\(([^)]*)\)", "Function"))

    for idx, line in enumerate(lines):
        line_num = idx + 1
        for regex, sym_type in patterns:
            match = re.search(regex, line)
            if match:
                name = match.group(1) if match.lastindex and match.lastindex >= 1 else sym_type
                raw_params = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
                params = []
                if raw_params:
                    for part in raw_params.split(","):
                        clean_p = clean_param_name(part, language)
                        if clean_p:
                            params.append(clean_p)
                symbols.append({
                    "type": sym_type,
                    "name": name,
                    "line": line_num,
                    "parameters": params,
                })

    if not symbols:
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str or line_str.startswith(("//", "#", "/*", "*", "--")):
                continue
            var_match = re.search(
                r"^\s*(?:let|const|var|val|int|float|double|char|string|auto|dim|\$)\s+([A-Za-z0-9_]+)",
                line,
            )
            if var_match:
                symbols.append({
                    "type": "Variable",
                    "name": var_match.group(1),
                    "line": idx + 1,
                    "parameters": [],
                })
            elif re.search(r"^\s*([A-Za-z0-9_]+)\s*=", line):
                assign_match = re.search(r"^\s*([A-Za-z0-9_]+)\s*=", line)
                var_name = assign_match.group(1)
                if var_name not in ("if", "for", "while", "return", "switch", "case"):
                    symbols.append({
                        "type": "Variable",
                        "name": var_name,
                        "line": idx + 1,
                        "parameters": [],
                    })
            elif re.search(r"^\s*(?:console\.log|printf|println|print|echo|System\.out\.println)\s*\(", line):
                symbols.append({
                    "type": "Output",
                    "name": "print()",
                    "line": idx + 1,
                    "parameters": [],
                })

    # For regex-analyzed languages, valid_syntax is None (not verified), NEVER True!
    return {
        "language": language,
        "valid_syntax": None,
        "syntax_status": "not_verified",
        "parser_used": "regex_heuristic",
        "syntax_message": f"Structural symbols extracted via regex heuristic; {language} compiler/parser not configured in local environment.",
        "symbols": symbols,
    }


def analyze(source: str, language: str) -> dict[str, Any]:
    lang = language.lower().strip()
    cap = get_language(lang)
    if not cap:
        raise ValueError(
            f"Unsupported language '{language}'. Supported languages: {', '.join(SUPPORTED_LANGUAGES)}"
        )

    if lang == "python":
        res = analyze_python(source)
    elif lang == "javascript":
        res = analyze_javascript(source)
    elif lang == "typescript":
        res = analyze_typescript(source)
    else:
        res = analyze_regex(source, lang)

    res["capabilities"] = cap.to_dict()
    res["fingerprint"] = compute_executable_fingerprint(source, lang)
    return res
