"""Tests for Hackathon 2026 strategic upgrades.

Covers:
1. Context-aware documentation (Google vs NumPy docstrings, parameter types, returns, raises)
2. Quality scoring engine explainability and determinism
3. Code preservation AST fingerprinting and mutation detection
4. Safe file/zip archive upload security (path traversal, size limits, secret exclusion)
5. 4-Stage Agentic workflow structured outputs
"""

import io
import os
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.analyzer import analyze, compute_executable_fingerprint
from app.main import app, generate_python_documentation
from app.quality import evaluate_documentation_quality
from app.verifier import verify, verify_structural_consistency


client = TestClient(app)


def test_numpy_style_docstring_generation():
    code = """def compute_compound_interest(principal: float, rate: float, periods: int) -> float:
    if principal < 0:
        raise ValueError("Principal must be non-negative")
    return principal * ((1.0 + rate) ** periods)
"""
    analysis = analyze(code, "python")
    doc_numpy = generate_python_documentation(code, analysis, doc_style="numpy")

    assert "Parameters" in doc_numpy
    assert "----------" in doc_numpy
    assert "principal : float" in doc_numpy
    assert "rate : float" in doc_numpy
    assert "periods : int" in doc_numpy
    assert "Returns" in doc_numpy
    assert "-------" in doc_numpy
    assert "float" in doc_numpy
    assert "Raises" in doc_numpy
    assert "------" in doc_numpy
    assert "ValueError" in doc_numpy


def test_google_style_docstring_generation():
    code = """def compute_compound_interest(principal: float, rate: float, periods: int) -> float:
    if principal < 0:
        raise ValueError("Principal must be non-negative")
    return principal * ((1.0 + rate) ** periods)
"""
    analysis = analyze(code, "python")
    doc_google = generate_python_documentation(code, analysis, doc_style="google")

    assert "Args:" in doc_google
    assert "principal (float):" in doc_google
    assert "rate (float):" in doc_google
    assert "Returns:" in doc_google
    assert "float:" in doc_google
    assert "Raises:" in doc_google
    assert "ValueError:" in doc_google


def test_quality_score_calculation():
    code = '''"""Module description."""

def add_numbers(a: int, b: int) -> int:
    """Adds two integers.

    Args:
        a (int): First operand.
        b (int): Second operand.

    Returns:
        int: The sum.
    """
    return a + b
'''
    analysis = analyze(code, "python")
    score_result = evaluate_documentation_quality(code, "python", analysis, "google")

    assert score_result["overall_score"] >= 90
    assert score_result["grade"] in ("A", "A+")
    assert score_result["parameter_coverage"] == 100.0
    assert score_result["return_coverage"] == 100.0
    assert "disclaimer" in score_result
    assert len(score_result["breakdown"]) == 5


def test_quality_score_penalizes_missing_params():
    undocumented_code = """def subtract(a: int, b: int) -> int:
    return a - b
"""
    analysis = analyze(undocumented_code, "python")
    score_result = evaluate_documentation_quality(undocumented_code, "python", analysis, "google")

    assert score_result["overall_score"] < 50
    assert score_result["grade"] in ("Needs Improvement", "C")
    assert score_result["parameter_coverage"] == 0.0


def test_executable_ast_fingerprint_preservation():
    code = """def multiply(x, y):
    return x * y
"""
    doc_code = '''def multiply(x, y):
    """Multiply two values."""
    # Compute product
    return x * y
'''
    fp_orig = compute_executable_fingerprint(code, "python")
    fp_prop = compute_executable_fingerprint(doc_code, "python")

    assert fp_orig["fingerprint"] == fp_prop["fingerprint"]
    assert fp_orig["algorithm"] == "sha256_ast_executable"


def test_executable_ast_fingerprint_detects_mutation():
    code = """def calculate(x, y):
    return x + y
"""
    mutated_code = """def calculate(x, y):
    # altered logic
    return x - y
"""
    fp_orig = compute_executable_fingerprint(code, "python")
    fp_prop = compute_executable_fingerprint(mutated_code, "python")

    assert fp_orig["fingerprint"] != fp_prop["fingerprint"]


def test_generate_endpoint_returns_4_stages(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    res = client.post(
        "/api/generate",
        json={
            "code": "def greet(name: str) -> str:\n    return f'Hello {name}'\n",
            "language": "python",
            "doc_style": "google",
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert "stages" in data
    assert len(data["stages"]) == 4
    stage_ids = [s["id"] for s in data["stages"]]
    assert stage_ids == ["analysis", "generation", "validation", "review"]
    assert "quality_score" in data
    assert "verification" in data
    assert data["doc_style"] == "google"


def test_safe_upload_single_python_file():
    py_content = b"def test_func():\n    return 42\n"
    res = client.post(
        "/api/upload-file",
        files={"file": ("test_script.py", io.BytesIO(py_content), "text/plain")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "single_file"
    assert data["language"] == "python"
    assert "def test_func" in data["code"]


def test_safe_upload_zip_archive_and_security_filters():
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("main.py", "def main():\n    print('Hello World')\n")
        zf.writestr(".env", "SECRET_KEY=supersecret123\n")
        zf.writestr("node_modules/bad_pkg/index.js", "malicious_code();\n")
        zf.writestr(".git/config", "repo_config\n")

    zip_buf.seek(0)
    res = client.post(
        "/api/upload-file",
        files={"file": ("project.zip", zip_buf, "application/zip")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "archive"
    assert data["language"] == "python"
    assert data["primary_file"] == "main.py"
    # Verify .env and node_modules were safely excluded
    file_paths = [f["path"] for f in data["files"]]
    assert "main.py" in file_paths
    assert not any(".env" in p for p in file_paths)
    assert not any("node_modules" in p for p in file_paths)
    assert not any(".git" in p for p in file_paths)


def test_safe_upload_rejects_path_traversal():
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("../../../etc/passwd", "root:x:0:0::/root:/bin/bash\n")

    zip_buf.seek(0)
    res = client.post(
        "/api/upload-file",
        files={"file": ("traversal.zip", zip_buf, "application/zip")},
    )
    # The traversal file is safely ignored, leading to 400 No valid files found
    assert res.status_code == 400


def test_safe_upload_rejects_oversized_file():
    oversized = b"a" * (2 * 1024 * 1024 + 10)  # > 2MB
    res = client.post(
        "/api/upload-file",
        files={"file": ("large.py", io.BytesIO(oversized), "text/plain")},
    )
    assert res.status_code == 413
