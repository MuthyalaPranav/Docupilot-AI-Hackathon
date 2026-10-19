import ast
import os
import re
import textwrap
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field
from .analyzer import analyze
from . import store

load_dotenv()
app = FastAPI(title="DocuPilot AI API", version="1.0.0")
raw_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
origins = [o.strip() for o in raw_origin.split(",") if o.strip()]
for dev_origin in ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]:
    if dev_origin not in origins:
        origins.append(dev_origin)
app.add_middleware(CORSMiddleware, allow_origins=origins if "*" not in origins else ["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
store.init_db()

SUPPORTED_LANGUAGES = (
    "python", "javascript", "typescript", "java", "c", "cpp", "csharp",
    "go", "php", "ruby", "swift", "kotlin", "rust", "sql"
)
SUPPORTED_LANGS_REGEX = "^(" + "|".join(SUPPORTED_LANGUAGES) + ")$"

class GenerateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=50000)
    language: str = Field(pattern=SUPPORTED_LANGS_REGEX)

class ApproveRequest(BaseModel):
    run_id: str
    code: str = Field(min_length=1, max_length=50000)

COMMON_PARAM_DESCS = {
    "price": "Base unit price or monetary amount before adjustments.",
    "discount": "Percentage discount rate applied to the total price (0-100).",
    "orders": "Collection of order records containing item, status, and total details.",
    "minimum_total": "Minimum value threshold required for an order to qualify.",
    "weight": "Shipment weight used to calculate base freight rates.",
    "distance": "Transit distance used to calculate distance-based surcharges.",
    "express": "Boolean flag indicating whether expedited transit priority applies.",
    "items": "List of items or elements to process.",
    "threshold": "Numerical cut-off boundary for qualifying elements.",
    "name": "Identifier name or string label.",
    "query": "Search query expression or filter criteria.",
    "data": "Input payload or dataset to evaluate.",
    "a": "First operand value.",
    "b": "Second operand value.",
    "x": "Primary input coordinate or numerical argument.",
    "y": "Secondary input coordinate or numerical argument.",
    "n": "Integer quantity or numeric parameter.",
}

def humanize_name(name: str) -> str:
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1 \2', name)
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s1)
    words = s2.replace('_', ' ').strip().split()
    if not words:
        return "Executes the operation based on provided inputs."
    verb = words[0].lower()
    if verb.endswith("e"):
        verb = verb.capitalize() + "s"
    elif verb.endswith(("ch", "sh", "ss", "x")):
        verb = verb.capitalize() + "es"
    elif verb.endswith("y") and verb[-2:] not in ("ay", "ey", "oy", "uy"):
        verb = verb[:-1].capitalize() + "ies"
    else:
        verb = verb.capitalize() + "s"
    rest = " ".join(words[1:]) if len(words) > 1 else "operation"
    return f"{verb} {rest} according to business rules and input parameters."

def describe_param(param: str) -> str:
    lower = param.lower().strip().lstrip("$")
    if lower in COMMON_PARAM_DESCS:
        return COMMON_PARAM_DESCS[lower]
    clean = param.replace('_', ' ').strip().lstrip("$")
    return f"Parameter representing the {clean} value."

def generate_python_documentation(code: str, analysis: dict) -> str:
    try:
        tree = ast.parse(code)
    except Exception:
        return code

    lines = code.splitlines()
    inserts: list[tuple[int, str]] = []

    # 1. Module Docstring
    has_module_doc = ast.get_docstring(tree) is not None
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

    if not has_module_doc:
        if funcs or classes:
            names = [c.name for c in classes] + [f.name for f in funcs]
            summary = f"Provides core implementations for {', '.join(names[:4])}."
        else:
            has_input = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "input" for n in ast.walk(tree))
            has_print = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "print" for n in ast.walk(tree))
            if has_input and has_print:
                summary = "Interactive console script.\nPrompts for user input, computes operations, and outputs results."
            elif has_input:
                summary = "Interactive user input processing script."
            elif has_print:
                summary = "Execution script with formatted console output."
            else:
                summary = "Operational workflow script."
        mod_doc = f'"""\n{summary}\n"""\n'
        inserts.append((0, mod_doc))

    # 2. Function & Class docstrings
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.get_docstring(node) is None:
            if not node.body:
                continue
            first_body = node.body[0]
            target_idx = first_body.lineno - 1
            body_line = lines[target_idx]
            leading = len(body_line) - len(body_line.lstrip(" "))
            indent = " " * (leading if leading > node.col_offset else (node.col_offset + 4))
            inner = indent + "    "
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                summary = humanize_name(node.name)
                args = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
                doc_lines = [
                    f'{indent}"""{summary}',
                    "",
                    f"{indent}Evaluates input arguments, performs calculation/processing, and returns results.",
                ]
                if args:
                    doc_lines.extend(["", f"{indent}Args:"])
                    for a in args:
                        doc_lines.append(f"{inner}{a}: {describe_param(a)}")
                has_return = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))
                if has_return:
                    doc_lines.extend(["", f"{indent}Returns:", f"{inner}Computed result derived from the processed inputs."])
                has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(node))
                if has_raise:
                    doc_lines.extend(["", f"{indent}Raises:", f"{inner}ValueError: If input values fail validation checks."])
                doc_lines.append(f'{indent}"""')
                inserts.append((target_idx, "\n".join(doc_lines)))
            else:
                summary = humanize_name(node.name)
                doc = f'{indent}"""{summary}\n\n{indent}Encapsulates state and logic for this component.\n{indent}"""'
                inserts.append((target_idx, doc))

    # 3. Inline Comments for statements
    def get_comment_for_stmt(node: ast.AST) -> str | None:
        if isinstance(node, ast.Assign):
            var_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            target_str = ", ".join(var_names) if var_names else "value"
            val = node.value
            if isinstance(val, ast.Call):
                f_name = getattr(val.func, "id", "")
                if f_name in ("int", "float", "str"):
                    if val.args and isinstance(val.args[0], ast.Call) and getattr(val.args[0].func, "id", "") == "input":
                        return f"# Prompt user and parse {f_name} input for '{target_str}'"
                    return f"# Cast expression to {f_name} and store in '{target_str}'"
                elif f_name == "input":
                    return f"# Prompt user for '{target_str}' string input"
                elif f_name:
                    return f"# Initialize '{target_str}' from {f_name}() result"
            elif isinstance(val, ast.BinOp):
                op_map = {ast.Add: "sum", ast.Sub: "difference", ast.Mult: "product", ast.Div: "quotient", ast.FloorDiv: "floor quotient", ast.Mod: "modulo remainder"}
                op_name = op_map.get(type(val.op), "arithmetic result")
                return f"# Calculate {op_name} and assign to '{target_str}'"
            elif isinstance(val, (ast.List, ast.Dict, ast.Set)):
                return f"# Initialize '{target_str}' collection"
            return f"# Initialize '{target_str}'"
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            return f"# Declare and initialize typed variable '{node.target.id}'"
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f_name = getattr(node.value.func, "id", "")
            if f_name == "print":
                args = node.value.args
                if args and isinstance(args[0], ast.BinOp) and isinstance(args[0].op, ast.Add):
                    return "# Calculate sum and display result to console"
                elif args and isinstance(args[0], ast.BinOp):
                    return "# Evaluate expression and print result to console"
                return "# Output results to console"
            elif f_name:
                return f"# Invoke {f_name}()"
        elif isinstance(node, ast.If):
            return "# Check conditional criteria and route control flow"
        elif isinstance(node, (ast.For, ast.While)):
            return "# Iterate through sequence elements"
        elif isinstance(node, ast.Return):
            return "# Return evaluated result to caller"
        return None

    commented_line_indices = set()
    for idx, l in enumerate(lines):
        if l.strip().startswith("#"):
            commented_line_indices.add(idx)
            commented_line_indices.add(idx + 1)

    candidate_stmts = list(tree.body)
    for f in funcs:
        candidate_stmts.extend(f.body)

    for stmt in candidate_stmts:
        target_idx = stmt.lineno - 1
        if target_idx in commented_line_indices or target_idx < 0 or target_idx >= len(lines):
            continue
        comment = get_comment_for_stmt(stmt)
        if comment:
            stmt_line = lines[target_idx]
            indent = " " * (len(stmt_line) - len(stmt_line.lstrip(" ")))
            inserts.append((target_idx, indent + comment))
            commented_line_indices.add(target_idx)

    for idx, doc in sorted(inserts, key=lambda x: (x[0], 0 if x[1].startswith('"""') else 1), reverse=True):
        lines.insert(idx, doc)

    return "\n".join(lines)

def mock_documentation(code: str, language: str, analysis: dict) -> str:
    lang = language.lower().strip()
    if lang == "python":
        return generate_python_documentation(code, analysis)

    # Other languages (Java, C, C++, C#, TypeScript, Go, PHP, Ruby, Swift, Kotlin, Rust, SQL, JavaScript)
    symbols = analysis.get("symbols") or []
    lines = code.splitlines()
    inserts = []

    # Filter function/class symbols vs variable symbols
    func_symbols = [s for s in symbols if s.get("type") not in ("Variable", "Output", "Query")]

    for sym in func_symbols:
        line_idx = sym.get("line", 1) - 1
        if line_idx < 0 or line_idx >= len(lines):
            continue
        line_text = lines[line_idx]
        indent = " " * (len(line_text) - len(line_text.lstrip(" ")))
        name = sym.get("name", "function")
        params = sym.get("parameters", [])
        summary = humanize_name(name)

        doc_lines = []
        if lang in ("javascript", "typescript"):
            doc_lines.append("/**")
            doc_lines.append(f" * {summary}")
            doc_lines.append(" *")
            for p in params:
                doc_lines.append(f" * @param {{*}} {p} - {describe_param(p)}")
            doc_lines.append(" * @returns {*} Computed result based on the processed inputs.")
            doc_lines.append(" */")
        elif lang == "java":
            doc_lines.append("/**")
            doc_lines.append(f" * {summary}")
            doc_lines.append(" *")
            for p in params:
                doc_lines.append(f" * @param {p} {describe_param(p)}")
            doc_lines.append(" * @return Computed result derived from the processed inputs.")
            doc_lines.append(" */")
        elif lang in ("c", "cpp"):
            doc_lines.append("/**")
            doc_lines.append(f" * @brief {summary}")
            doc_lines.append(" *")
            for p in params:
                doc_lines.append(f" * @param {p} {describe_param(p)}")
            doc_lines.append(" * @return Computed result derived from the processed inputs.")
            doc_lines.append(" */")
        elif lang == "csharp":
            doc_lines.append("/// <summary>")
            doc_lines.append(f"/// {summary}")
            doc_lines.append("/// </summary>")
            for p in params:
                doc_lines.append(f'/// <param name="{p}">{describe_param(p)}</param>')
            doc_lines.append("/// <returns>Computed result derived from the processed inputs.</returns>")
        elif lang == "go":
            doc_lines.append(f"// {name} {summary.lower()}")
            for p in params:
                doc_lines.append(f"// {p}: {describe_param(p)}")
            doc_lines.append("// Returns the computed outcome based on input conditions.")
        elif lang == "php":
            doc_lines.append("/**")
            doc_lines.append(f" * {summary}")
            doc_lines.append(" *")
            for p in params:
                doc_lines.append(f" * @param mixed ${p} {describe_param(p)}")
            doc_lines.append(" * @return mixed Computed result derived from the processed inputs.")
            doc_lines.append(" */")
        elif lang == "ruby":
            doc_lines.append(f"# {summary}")
            doc_lines.append("#")
            for p in params:
                doc_lines.append(f"# @param {p} [Object] {describe_param(p)}")
            doc_lines.append("# @return [Object] Computed result derived from the processed inputs.")
        elif lang == "swift":
            doc_lines.append(f"/// {summary}")
            if params:
                doc_lines.append("///")
                doc_lines.append("/// - Parameters:")
                for p in params:
                    doc_lines.append(f"///   - {p}: {describe_param(p)}")
            doc_lines.append("/// - Returns: Computed result derived from the processed inputs.")
        elif lang == "kotlin":
            doc_lines.append("/**")
            doc_lines.append(f" * {summary}")
            doc_lines.append(" *")
            for p in params:
                doc_lines.append(f" * @param {p} {describe_param(p)}")
            doc_lines.append(" * @return Computed result derived from the processed inputs.")
            doc_lines.append(" */")
        elif lang == "rust":
            doc_lines.append(f"/// {summary}")
            if params:
                doc_lines.append("///")
                doc_lines.append("/// # Arguments")
                doc_lines.append("///")
                for p in params:
                    doc_lines.append(f"/// * `{p}` - {describe_param(p)}")
            doc_lines.append("///")
            doc_lines.append("/// # Returns")
            doc_lines.append("///")
            doc_lines.append("/// * Computed result derived from the processed inputs.")
        elif lang == "sql":
            doc_lines.append("-- ============================================================================")
            doc_lines.append(f"-- Definition: {name}")
            doc_lines.append(f"-- Purpose: {summary}")
            doc_lines.append("-- ============================================================================")

        if doc_lines:
            indented = "\n".join(indent + l for l in doc_lines)
            inserts.append((line_idx, indented))

    # If no function symbols found, add header documentation and inline statement comments
    if not func_symbols:
        header = ""
        c_pfx = "// "
        if lang in ("javascript", "typescript"):
            header = "/**\n * Application script and workflow execution.\n * Handles user inputs, data operations, and output results.\n */\n"
        elif lang == "java":
            header = "/**\n * Application routine for data operations and computational workflow.\n */\n"
        elif lang in ("c", "cpp"):
            header = "/**\n * @file\n * @brief Application routine and operational logic execution.\n */\n"
        elif lang == "csharp":
            header = "/// <summary>\n/// Application script executing operational logic and workflow.\n/// </summary>\n"
        elif lang == "go":
            header = "// Package main provides operational script routines and data workflows.\n"
        elif lang == "php":
            header = "/**\n * Script workflow execution and operations.\n */\n"
        elif lang == "ruby":
            c_pfx = "# "
            header = "# Module providing execution logic and data operations.\n"
        elif lang == "swift":
            header = "/// Application routine executing data processing and workflows.\n"
        elif lang == "kotlin":
            header = "/**\n * Application script executing routine logic.\n */\n"
        elif lang == "rust":
            header = "//! Application module executing data operations and workflow.\n"
        elif lang == "sql":
            c_pfx = "-- "
            header = "-- ============================================================================\n-- Script: Database Query and Data Manipulation\n-- ============================================================================\n"

        if header:
            inserts.append((0, header))

        # Add statement comments for lines
        for idx, line in enumerate(lines):
            l_strip = line.strip()
            if not l_strip or l_strip.startswith(("//", "#", "/*", "*", "--")):
                continue
            indent = " " * (len(line) - len(line.lstrip(" ")))
            if re.search(r'(?:prompt|scanf|cin\s*>>|readline|Console\.ReadLine)\s*\(?', l_strip, re.I):
                inserts.append((idx, f"{indent}{c_pfx}Read user input from standard stream"))
            elif re.search(r'(?:console\.log|printf|cout\s*<<|println|print|echo|System\.out\.println)\s*\(?', l_strip, re.I):
                inserts.append((idx, f"{indent}{c_pfx}Output evaluated result to console"))
            elif re.search(r'^\s*(?:let|const|var|val|int|float|double|char|string|\$)\s+([A-Za-z0-9_]+)', l_strip):
                inserts.append((idx, f"{indent}{c_pfx}Declare and initialize variable"))
            elif re.search(r'^\s*if\s*\(', l_strip):
                inserts.append((idx, f"{indent}{c_pfx}Evaluate condition and route control flow"))

    if inserts:
        for idx, doc in sorted(inserts, key=lambda x: (x[0], 0 if ("/**" in x[1] or "/*" in x[1] or "-- ===" in x[1]) else 1), reverse=True):
            lines.insert(idx, doc)
        return "\n".join(lines)

    comment_prefix = "-- " if lang == "sql" else ("# " if lang == "ruby" else "// ")
    return f"{comment_prefix}Module documentation for {lang}\n" + code

def generate_with_openai(code: str, language: str, analysis: dict) -> tuple[str, str]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return mock_documentation(code, language, analysis), "mock"
    client = OpenAI(api_key=key)
    raw_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    model = "gpt-4o-mini" if raw_model in ("gpt-4.1-mini", "") else raw_model
    prompt = f"""You are an expert senior software engineer and technical documentation specialist.
Your task: Return ONLY the complete updated source code with deep, crystal-clear, explanatory docstrings and insightful inline comments.

STRICT INSTRUCTIONS FOR CLARITY AND QUALITY (NO VAGUE ANSWERS):
1. ZERO VAGUE PLACEHOLDERS:
   - Absolutely NEVER use generic phrases such as "Describe what this function does", "Processes data", "Executes logic", or "Describe x".
   - Every single docstring and comment must specifically describe the ACTUAL business logic, mathematical formulas, constraints, and operations present in the code.

2. LANGUAGE-SPECIFIC DOCUMENTATION CONVENTIONS:
   - Python: PEP 257 / Google standard docstrings using \"\"\" triple quotes with "Args:", "Returns:", and "Raises:" sections, plus top-level module docstrings.
   - Java: Standard Javadoc /** ... */ with descriptive summary, @param, @return, and @throws tags.
   - C#: XML documentation comments using /// <summary> ... </summary>, /// <param name="..."> ... </param>, and /// <returns> ... </returns>.
   - JavaScript & TypeScript: Comprehensive JSDoc/TSDoc /** ... */ with @param {{type}}, @returns {{type}}, and @throws {{type}}.
   - C & C++: Doxygen style /** ... @brief ... @param ... @return ... */ or clear /* ... */ block comments.
   - Go: Idiomatic Go doc format (single-line comments `// FunctionName ...` immediately preceding declarations).
   - PHP: PHPDoc /** ... */ with @param type $name, @return type, and @throws type.
   - Ruby: YARD / RDoc conventions using # comments with @param and @return tags.
   - Swift: Swift documentation markup using /// with "- Parameters:" and "- Returns:" sections.
   - Kotlin: KDoc /** ... */ with @param and @return tags.
   - Rust: Rustdoc /// with markdown headings "# Arguments", "# Returns", and "# Errors".
   - SQL: Professional SQL comments using -- or /* ... */ documenting query/procedure purpose, tables, CTEs, joins, and parameters.

3. INSIGHTFUL INLINE COMMENTS:
   - Add concise inline comments above critical non-obvious statements (e.g. edge-case guard checks, sorting criteria, mathematical calculations, filtering loops, user inputs, outputs).
   - Explain the "WHY" behind the implementation, not merely restating the syntax.

4. PRESERVE ORIGINAL CODE:
   - Preserve 100% of executable statements, variable names, functions, and semantics. Do not refactor or delete any existing logic.
   - Return ONLY the updated code without markdown fences (no ```python or ```javascript) and without any conversational introduction or conclusion.

Language: {language}
Parsed structural hints: {analysis}

SOURCE CODE:
{code}"""

    output = ""
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert code documentation assistant. Return only updated code with docstrings and comments without markdown backticks."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        if completion.choices and completion.choices[0].message:
            output = completion.choices[0].message.content or ""
    except Exception as chat_err:
        if hasattr(client, "responses"):
            try:
                resp = client.responses.create(model=model, input=prompt)
                output = getattr(resp, "output_text", "") or ""
            except Exception:
                raise chat_err
        else:
            raise chat_err

    output = output.strip()
    if output.startswith("```"):
        lines = output.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        output = "\n".join(lines).strip()
    return output, "openai"

def verify_brackets(code: str) -> tuple[bool, str]:
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
                    return False, f"Mismatched bracket '{ch}'."
                stack.pop()
        i += 1
    if stack:
        return False, f"Unclosed bracket '{stack[-1]}'."
    return True, "Structure and syntax integrity verified."

def verify(code: str, language: str) -> dict:
    lang = language.lower().strip()
    checks = []
    syntax_ok = False
    syntax_message = ""
    try:
        if lang == "python":
            ast.parse(code)
            syntax_ok = True
            syntax_message = "Python AST parse passed."
            tree = ast.parse(code)
            targets = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            if targets > 0:
                documented = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.get_docstring(n))
                checks.append({"name": "Documentation coverage", "passed": documented == targets, "details": f"{documented}/{targets} functions/classes have docstrings."})
            else:
                has_mod = bool(ast.get_docstring(tree))
                comment_lines = sum(1 for l in code.splitlines() if l.strip().startswith("#"))
                checks.append({"name": "Script documentation", "passed": has_mod or comment_lines > 0, "details": f"Module docstring: {'Present' if has_mod else 'None'}, {comment_lines} comment line(s)."})
        elif lang == "javascript":
            import esprima
            try:
                esprima.parseScript(code, {"loc": True, "tolerant": False})
            except Exception:
                esprima.parseModule(code, {"loc": True, "tolerant": False})
            syntax_ok = True
            syntax_message = "JavaScript syntax parse passed."
            documented = code.count("/**") + code.count("//") + code.count("/*")
            checks.append({"name": "Documentation presence", "passed": documented > 0, "details": f"Found documentation elements ({documented} block(s)/line(s))."})
        else:
            # Multi-language verification
            ok, msg = verify_brackets(code)
            syntax_ok = ok
            syntax_message = f"{lang.capitalize()} syntax integrity: {msg}"
            
            # Check language documentation presence
            if lang in ("typescript", "java", "kotlin", "php"):
                doc_count = code.count("/**") + code.count("//")
                doc_name = "Javadoc/KDoc/JSDoc"
            elif lang in ("c", "cpp"):
                doc_count = code.count("/**") + code.count("/*") + code.count("//")
                doc_name = "Doxygen/Block comment"
            elif lang in ("csharp", "swift", "rust"):
                doc_count = code.count("///") + code.count("//")
                doc_name = "Doc comment (///)"
            elif lang == "go":
                doc_count = code.count("//")
                doc_name = "Go doc (//)"
            elif lang == "ruby":
                doc_count = code.count("#")
                doc_name = "Ruby comment (#)"
            elif lang == "sql":
                doc_count = code.count("--") + code.count("/*")
                doc_name = "SQL comment (--)"
            else:
                doc_count = code.count("//") + code.count("/*") + code.count("#")
                doc_name = "Comment"
                
            checks.append({
                "name": f"{doc_name} presence",
                "passed": doc_count > 0,
                "details": f"Found documentation elements ({doc_count} block(s)/line(s))."
            })
    except Exception as exc:
        syntax_message = str(exc)

    checks.insert(0, {"name": "Syntax", "passed": syntax_ok, "details": syntax_message})
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "note": "Static checks only; passing syntax does not prove behavioral equivalence."}

@app.get("/")
def root():
    return {"name": "DocuPilot AI API", "status": "ok", "docs": "/docs"}

@app.get("/api/health")
def health():
    return {"status": "healthy"}

@app.post("/api/generate")
def generate(req: GenerateRequest):
    try:
        analysis = analyze(req.code, req.language)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Code parsing failed: {exc}")
    try:
        proposed, mode = generate_with_openai(req.code, req.language, analysis)
        gen_error = None
    except Exception as exc:
        proposed = mock_documentation(req.code, req.language, analysis)
        mode = "mock"
        err_msg = str(exc)
        if "insufficient_quota" in err_msg or "credit_balance_exhausted" in err_msg or "429" in err_msg:
            gen_error = "OpenAI API quota exceeded (insufficient balance). Generated using DocuPilot Local Engine."
        elif "invalid_api_key" in err_msg or "Incorrect API key" in err_msg:
            gen_error = "Invalid OpenAI API key. Generated using DocuPilot Local Engine."
        else:
            gen_error = f"OpenAI unavailable ({err_msg[:60]}...). Generated using DocuPilot Local Engine."

    if not proposed.strip():
        raise HTTPException(status_code=502, detail="The generator returned empty code.")
    run_id = store.save_run(req.language, req.code, proposed, analysis, mode)
    return {"run_id": run_id, "language": req.language, "analysis": analysis, "proposed_code": proposed, "mode": mode, "status": "pending_review", "warning": gen_error}

@app.post("/api/approve")
def approve(req: ApproveRequest):
    run = store.get_run(req.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run["status"] != "pending_review":
        raise HTTPException(status_code=409, detail="This run has already been reviewed.")
    verification = verify(req.code, run["language"])
    updated = store.approve_run(req.run_id, req.code, verification)
    if not updated:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"run_id": req.run_id, "status": "approved_verified" if verification["passed"] else "approved_checks_failed", "verification": verification, "final_code": req.code}

@app.get("/api/history")
def history():
    return {"items": store.list_runs()}

@app.get("/api/history/{run_id}")
def history_item(run_id: str):
    item = store.get_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="Run not found.")
    return item
