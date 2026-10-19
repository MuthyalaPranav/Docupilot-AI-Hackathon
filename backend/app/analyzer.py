import ast
import json
import re
from typing import Any

SUPPORTED_LANGUAGES = (
    "python", "javascript", "typescript", "java", "c", "cpp", "csharp",
    "go", "php", "ruby", "swift", "kotlin", "rust", "sql"
)

def analyze_python(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append({
                "type": node.__class__.__name__,
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "parameters": [a.arg for a in node.args.args if a.arg not in ("self", "cls")] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else [],
                "has_docstring": ast.get_docstring(node) is not None,
            })
    # If no functions or classes exist, detect top-level script statements and variables
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
                            "has_docstring": False
                        })
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                symbols.append({
                    "type": "Variable",
                    "name": node.target.id,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "parameters": [],
                    "has_docstring": False
                })
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func_name = getattr(node.value.func, "id", None) or getattr(node.value.func, "attr", "call")
                symbols.append({
                    "type": "Call",
                    "name": f"{func_name}()",
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "parameters": [],
                    "has_docstring": False
                })
    return {"language": "python", "valid_syntax": True, "symbols": symbols}

def analyze_javascript(source: str) -> dict[str, Any]:
    try:
        import esprima
        try:
            tree = esprima.parseScript(source, {"loc": True, "tolerant": False})
        except Exception:
            tree = esprima.parseModule(source, {"loc": True, "tolerant": False})
        symbols = []
        def walk(node):
            if isinstance(node, dict):
                typ = node.get("type")
                if typ in ("FunctionDeclaration", "ClassDeclaration", "MethodDefinition", "ArrowFunctionExpression", "FunctionExpression"):
                    name = None
                    ident = node.get("id")
                    if isinstance(ident, dict):
                        name = ident.get("name")
                    if not name and isinstance(node.get("key"), dict):
                        name = node["key"].get("name")
                    params = []
                    for p in node.get("params", []):
                        if isinstance(p, dict):
                            if p.get("type") == "AssignmentPattern" and isinstance(p.get("left"), dict):
                                params.append(p["left"].get("name") or "param")
                            else:
                                params.append(p.get("name") or p.get("type", "parameter"))
                        elif isinstance(p, str):
                            params.append(p)
                    symbols.append({"type": typ, "name": name or "(anonymous)", "line": (node.get("loc") or {}).get("start", {}).get("line"), "parameters": params})
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        walk(tree.toDict())
        return {"language": "javascript", "valid_syntax": True, "symbols": symbols}
    except Exception:
        # Fallback to regex analysis
        return analyze_regex(source, "javascript")

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

def analyze_regex(source: str, language: str) -> dict[str, Any]:
    symbols = []
    lines = source.splitlines()
    patterns: list[tuple[str, str]] = []

    if language in ("c", "cpp"):
        patterns.append((r'^\s*(?:(?:inline|static|virtual|const|extern|constexpr)\s+)*(?:[\w:*&<>]+\s+)+(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*(?:\{|;)?$', "Function"))
        patterns.append((r'^\s*(?:class|struct)\s+(\w+)', "Class" if language == "cpp" else "Struct"))
    elif language == "java":
        patterns.append((r'^\s*(?:public|protected|private|static|final|abstract|synchronized|\s)*\s+(?:[\w<>\[\],]+\s+)+(\w+)\s*\(([^)]*)\)', "Method"))
        patterns.append((r'^\s*(?:public|protected|private|\s)*\s*(?:class|interface|enum|record)\s+(\w+)', "Class"))
    elif language == "csharp":
        patterns.append((r'^\s*(?:public|protected|private|static|async|virtual|override|abstract|\s)*\s*(?:[\w<>\[\],?]+\s+)+(\w+)\s*\(([^)]*)\)', "Method"))
        patterns.append((r'^\s*(?:public|protected|private|\s)*\s*(?:class|interface|struct|record)\s+(\w+)', "Class"))
    elif language == "typescript":
        patterns.append((r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)', "Function"))
        patterns.append((r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*(?::\s*[^=]+)?\s*=>', "ArrowFunction"))
        patterns.append((r'^\s*(?:export\s+)?(?:class|interface|type)\s+(\w+)', "Type"))
    elif language == "go":
        patterns.append((r'^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)', "Function"))
        patterns.append((r'^\s*type\s+(\w+)\s+(?:struct|interface)', "Type"))
    elif language == "php":
        patterns.append((r'^\s*(?:public|protected|private|static|\s)*\s*function\s+(\w+)\s*\(([^)]*)\)', "Function"))
        patterns.append((r'^\s*(?:abstract|final|\s)*\s*class\s+(\w+)', "Class"))
    elif language == "ruby":
        patterns.append((r'^\s*def\s+([A-Za-z0-9_!?]+)(?:\s*\(([^)]*)\))?', "Method"))
        patterns.append((r'^\s*(?:class|module)\s+([A-Za-z0-9_:]+)', "Class"))
    elif language == "swift":
        patterns.append((r'^\s*(?:public|private|fileprivate|internal|open|static|\s)*\s*func\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)', "Function"))
        patterns.append((r'^\s*(?:class|struct|protocol|enum)\s+(\w+)', "Type"))
    elif language == "kotlin":
        patterns.append((r'^\s*(?:public|private|protected|internal|override|suspend|\s)*\s*fun\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)', "Function"))
        patterns.append((r'^\s*(?:data\s+)?(?:class|interface|object)\s+(\w+)', "Class"))
    elif language == "rust":
        patterns.append((r'^\s*(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)', "Function"))
        patterns.append((r'^\s*(?:pub(?:\([^)]+\))?\s+)?(?:struct|enum|trait)\s+(\w+)', "Type"))
    elif language == "sql":
        patterns.append((r'(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+([A-Za-z0-9_]+)', "Procedure"))
        patterns.append((r'(?i)^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)\s+([A-Za-z0-9_]+)', "Table"))
        patterns.append((r'(?i)^\s*(?:SELECT|INSERT|UPDATE|DELETE|WITH)\s+', "Query"))
    else:
        # Generic function pattern fallback
        patterns.append((r'^\s*(?:def|func|function|fn)\s+(\w+)\s*\(([^)]*)\)', "Function"))

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
                    "parameters": params
                })
    if not symbols:
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str or line_str.startswith(("//", "#", "/*", "*", "--")):
                continue
            var_match = re.search(r'^\s*(?:let|const|var|val|int|float|double|char|string|auto|dim|\$)\s+([A-Za-z0-9_]+)', line)
            if var_match:
                symbols.append({"type": "Variable", "name": var_match.group(1), "line": idx + 1, "parameters": []})
            elif re.search(r'^\s*([A-Za-z0-9_]+)\s*=', line):
                assign_match = re.search(r'^\s*([A-Za-z0-9_]+)\s*=', line)
                var_name = assign_match.group(1)
                if var_name not in ("if", "for", "while", "return", "switch", "case"):
                    symbols.append({"type": "Variable", "name": var_name, "line": idx + 1, "parameters": []})
            elif re.search(r'^\s*(?:console\.log|printf|println|print|echo|System\.out\.println)\s*\(', line):
                symbols.append({"type": "Output", "name": "print()", "line": idx + 1, "parameters": []})

    return {"language": language, "valid_syntax": True, "symbols": symbols}

def analyze(source: str, language: str) -> dict[str, Any]:
    lang = language.lower().strip()
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language '{language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}")
    if lang == "python":
        return analyze_python(source)
    if lang == "javascript":
        return analyze_javascript(source)
    return analyze_regex(source, lang)
