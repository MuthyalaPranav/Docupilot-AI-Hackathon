import pytest
from fastapi.testclient import TestClient
from app.analyzer import analyze, SUPPORTED_LANGUAGES
from app.main import app, verify, mock_documentation

client = TestClient(app)

LANG_SAMPLES = {
    "python": "def calculate_discount(price, discount):\n    if price <= 0:\n        return 0\n    return price - (price * discount / 100)\n",
    "javascript": "function calculateShipping(weight, distance) {\n    return weight * 2.5 + distance * 0.4;\n}",
    "typescript": "export function computeTotal(items: number[], rate: number): number {\n    return items.reduce((a, b) => a + b, 0) * rate;\n}",
    "java": "public class OrderProcessor {\n    public double calculateDiscount(double price, double discount) {\n        return price * discount;\n    }\n}",
    "c": "float calculate_discount(float price, float discount) {\n    return price - discount;\n}",
    "cpp": "class DiscountCalculator {\npublic:\n    double calculateDiscount(double price, double discount) {\n        return price * discount;\n    }\n};",
    "csharp": "public class ShoppingCart {\n    public decimal CalculateShipping(decimal weight, decimal distance) {\n        return weight * 2.5m;\n    }\n}",
    "go": "package shipping\n\nfunc CalculateShipping(weight float64, distance float64) float64 {\n    return weight * 2.5;\n}",
    "php": "<?php\nfunction calculateDiscount($price, $discount) {\n    return $price - $discount;\n}",
    "ruby": "def calculate_discount(price, discount)\n    price * discount\nend",
    "swift": "func calculateShipping(weight: Double, distance: Double) -> Double {\n    return weight * 2.5\n}",
    "kotlin": "fun calculateDiscount(price: Double, discount: Double): Double {\n    return price * discount\n}",
    "rust": "pub fn calculate_discount(price: f64, discount: f64) -> f64 {\n    price * discount\n}",
    "sql": "CREATE FUNCTION calculate_discount(price DECIMAL, discount DECIMAL) RETURNS DECIMAL BEGIN RETURN price; END;",
}

def test_python_analysis():
    result = analyze("def add(a, b):\n    return a + b\n", "python")
    assert result["valid_syntax"]
    assert any(s["name"] == "add" and s["parameters"] == ["a", "b"] for s in result["symbols"])

def test_javascript_analysis():
    result = analyze("function add(a, b) { return a + b; }", "javascript")
    assert result["valid_syntax"]
    assert any(s["name"] == "add" for s in result["symbols"])

def test_javascript_es6_module_analysis():
    code = "export function multiply(x, y) { return x * y; }"
    result = analyze(code, "javascript")
    assert result["valid_syntax"]
    assert any(s["name"] == "multiply" for s in result["symbols"])

@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_all_languages_supported_analysis(lang):
    code = LANG_SAMPLES[lang]
    result = analyze(code, lang)
    assert result["valid_syntax"]
    assert result["language"] == lang
    assert len(result["symbols"]) > 0

@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_all_languages_mock_documentation_and_verify(lang):
    code = LANG_SAMPLES[lang]
    analysis = analyze(code, lang)
    doc_code = mock_documentation(code, lang, analysis)
    assert len(doc_code) > len(code)
    v = verify(doc_code, lang)
    assert v["passed"], f"Verification failed for {lang}: {v}"

def test_python_verification_fails_invalid_syntax():
    result = verify("def broken(:\n    pass", "python")
    assert not result["passed"]

def test_bracket_mismatch_verification_fails():
    result = verify("public class Broken { void test() { return; }", "java")
    assert not result["passed"]
    assert any("bracket" in c.get("details", "").lower() for c in result["checks"])

def test_api_full_workflow(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}

    # Test workflow with TypeScript
    gen = client.post("/api/generate", json={
        "language": "typescript",
        "code": LANG_SAMPLES["typescript"]
    })
    assert gen.status_code == 200
    gen_data = gen.json()
    assert "run_id" in gen_data
    run_id = gen_data["run_id"]

    # Approve
    appr = client.post("/api/approve", json={
        "run_id": run_id,
        "code": gen_data["proposed_code"]
    })
    assert appr.status_code == 200
    appr_data = appr.json()
    assert appr_data["status"] == "approved_verified"
    assert appr_data["verification"]["passed"] is True

    # History
    hist = client.get("/api/history")
    assert hist.status_code == 200
    items = hist.json().get("items", [])
    assert any(item["id"] == run_id for item in items)

def test_python_procedural_script_documentation():
    code = "a = int(input())\nb = int(input())\nprint(a + b)\n"
    analysis = analyze(code, "python")
    assert analysis["valid_syntax"]
    assert len(analysis["symbols"]) > 0
    assert any(s["name"] == "a" for s in analysis["symbols"])
    assert any(s["name"] == "b" for s in analysis["symbols"])

    doc_code = mock_documentation(code, "python", analysis)
    assert '"""' in doc_code
    assert "# " in doc_code
    assert "a = int(input())" in doc_code
    assert "print(a + b)" in doc_code

    v = verify(doc_code, "python")
    assert v["passed"]

