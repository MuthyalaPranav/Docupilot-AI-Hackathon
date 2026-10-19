import { useEffect, useState } from "react";
import { Activity, ArrowDownToLine, Bot, Check, CheckCircle2, Code2, FileCode2, History, LoaderCircle, Play, RefreshCw, ShieldCheck, Sparkles, WandSparkles, X } from "lucide-react";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const LANGUAGES = [
  { id: "python", name: "Python", ext: "py" },
  { id: "javascript", name: "JavaScript", ext: "js" },
  { id: "typescript", name: "TypeScript", ext: "ts" },
  { id: "java", name: "Java", ext: "java" },
  { id: "c", name: "C", ext: "c" },
  { id: "cpp", name: "C++", ext: "cpp" },
  { id: "csharp", name: "C#", ext: "cs" },
  { id: "go", name: "Go", ext: "go" },
  { id: "php", name: "PHP", ext: "php" },
  { id: "ruby", name: "Ruby", ext: "rb" },
  { id: "swift", name: "Swift", ext: "swift" },
  { id: "kotlin", name: "Kotlin", ext: "kt" },
  { id: "rust", name: "Rust", ext: "rs" },
  { id: "sql", name: "SQL", ext: "sql" },
];

export const SAMPLES: Record<string, string> = {
  python: `def calculate_discount(price, discount):
    if price <= 0 or discount < 0 or discount > 100:
        return 0
    return price - (price * discount / 100)

def summarize_orders(orders, minimum_total=0):
    eligible = []
    for order in orders:
        if order.get("status") == "paid":
            total = sum(item["price"] * item["quantity"] for item in order.get("items", []))
            if total >= minimum_total:
                eligible.append({"id": order["id"], "total": total})
    return sorted(eligible, key=lambda order: order["total"], reverse=True)`,

  javascript: `function calculateShipping(weight, distance, express = false) {
  if (weight <= 0 || distance < 0) {
    throw new Error("Invalid shipping inputs");
  }
  const base = weight * 2.5;
  const distanceFee = distance > 100 ? distance * 0.8 : distance * 0.4;
  const surcharge = express ? base * 0.5 : 0;
  return Math.round((base + distanceFee + surcharge) * 100) / 100;
}`,

  typescript: `interface CartItem {
  id: string;
  price: number;
  quantity: number;
}

export function computeCartTotal(items: CartItem[], taxRate: number = 0.08): number {
  if (taxRate < 0) {
    throw new RangeError("Tax rate cannot be negative");
  }
  const subtotal = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  const tax = subtotal * taxRate;
  return Math.round((subtotal + tax) * 100) / 100;
}`,

  java: `public class OrderProcessor {
    public double calculateDiscount(double price, double discount) {
        if (price <= 0 || discount < 0 || discount > 100) {
            return 0.0;
        }
        return price - (price * discount / 100.0);
    }
}`,

  c: `#include <stdio.h>

float calculate_discount(float price, float discount) {
    if (price <= 0 || discount < 0 || discount > 100) {
        return 0.0f;
    }
    return price - (price * discount / 100.0f);
}`,

  cpp: `class DiscountCalculator {
public:
    double calculateDiscount(double price, double discount) {
        if (price <= 0 || discount < 0 || discount > 100) {
            return 0.0;
        }
        return price - (price * discount / 100.0);
    }
};`,

  csharp: `public class ShoppingCart {
    public decimal CalculateShipping(decimal weight, decimal distance, bool express = false) {
        if (weight <= 0 || distance < 0) {
            throw new System.ArgumentException("Invalid shipping parameters");
        }
        decimal baseRate = weight * 2.5m;
        decimal distanceFee = distance > 100 ? distance * 0.8m : distance * 0.4m;
        decimal surcharge = express ? baseRate * 0.5m : 0m;
        return baseRate + distanceFee + surcharge;
    }
}`,

  go: `package shipping

import "errors"

func CalculateShipping(weight float64, distance float64, express bool) (float64, error) {
    if weight <= 0 || distance < 0 {
        return 0, errors.New("invalid shipping inputs")
    }
    base := weight * 2.5
    fee := distance * 0.4
    if distance > 100 {
        fee = distance * 0.8
    }
    surcharge := 0.0
    if express {
        surcharge = base * 0.5
    }
    return base + fee + surcharge, nil
}`,

  php: `<?php

function calculateDiscount(float $price, float $discount): float {
    if ($price <= 0 || $discount < 0 || $discount > 100) {
        return 0.0;
    }
    return $price - ($price * $discount / 100.0);
}`,

  ruby: `def calculate_discount(price, discount)
  return 0 if price <= 0 || discount < 0 || discount > 100
  price - (price * discount / 100.0)
end`,

  swift: `func calculateShipping(weight: Double, distance: Double, express: Bool = false) -> Double {
    guard weight > 0 && distance >= 0 else {
        return 0.0
    }
    let base = weight * 2.5
    let distanceFee = distance > 100 ? distance * 0.8 : distance * 0.4
    let surcharge = express ? base * 0.5 : 0.0
    return base + distanceFee + surcharge
}`,

  kotlin: `fun calculateDiscount(price: Double, discount: Double): Double {
    if (price <= 0 || discount < 0.0 || discount > 100.0) {
        return 0.0
    }
    return price - (price * discount / 100.0)
}`,

  rust: `pub fn calculate_discount(price: f64, discount: f64) -> Result<f64, &'static str> {
    if price <= 0.0 || discount < 0.0 || discount > 100.0 {
        return Err("Invalid price or discount percentage");
    }
    Ok(price - (price * discount / 100.0))
}`,

  sql: `CREATE OR REPLACE FUNCTION calculate_discount(price DECIMAL(10,2), discount DECIMAL(5,2))
RETURNS DECIMAL(10,2) AS $$
BEGIN
    IF price <= 0 OR discount < 0 OR discount > 100 THEN
        RETURN 0.00;
    END IF;
    RETURN price - (price * discount / 100.0);
END;
$$ LANGUAGE plpgsql;`,
};

type Generated = { run_id: string; language: string; analysis: any; proposed_code: string; mode: string; status: string; warning?: string | null };
type Verify = { passed: boolean; checks: {name:string;passed:boolean;details:string}[]; note:string };
type HistoryItem = {id:string;created_at:string;language:string;status:string;mode:string};

export default function App() {
  const [language, setLanguage] = useState("python");
  const [source, setSource] = useState(SAMPLES.python);
  const [generated, setGenerated] = useState<Generated | null>(null);
  const [edited, setEdited] = useState("");
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [message, setMessage] = useState("");
  const [verification, setVerification] = useState<Verify | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [health, setHealth] = useState("checking");

  async function refreshHistory() {
    try { const r = await fetch(`${API}/api/history`); const d = await r.json(); setHistory(d.items || []); }
    catch { /* API may be starting */ }
  }
  useEffect(() => {
    fetch(`${API}/api/health`).then(r => r.ok ? setHealth("online") : setHealth("offline")).catch(() => setHealth("offline"));
    refreshHistory();
  }, []);

  function changeLanguage(value: string) {
    setLanguage(value);
    setSource(SAMPLES[value] || SAMPLES.python);
    setGenerated(null);
    setVerification(null);
    setMessage("");
  }
  async function generate() {
    setLoading(true); setMessage(""); setVerification(null); setGenerated(null);
    try {
      const response = await fetch(`${API}/api/generate`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({code:source,language})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Generation failed");
      setGenerated(data); setEdited(data.proposed_code);
      setMessage("Code documentation proposal generated. Review every change before approval.");
      await refreshHistory();
    } catch (e:any) { setMessage(e.message || "Could not reach the backend."); }
    finally { setLoading(false); }
  }
  async function approve() {
    if (!generated) return;
    setApproving(true); setMessage("");
    try {
      const response = await fetch(`${API}/api/approve`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({run_id:generated.run_id,code:edited})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Verification failed");
      setVerification(data.verification);
      setMessage(data.verification.passed ? "Review recorded. All configured checks passed." : "Review recorded, but one or more checks failed. Do not claim the code is fully verified.");
      await refreshHistory();
    } catch (e:any) { setMessage(e.message || "Could not approve changes."); }
    finally { setApproving(false); }
  }
  function download() {
    const blob = new Blob([edited], {type:"text/plain;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const found = LANGUAGES.find(l => l.id === language);
    const ext = found ? found.ext : "txt";
    a.href = url;
    a.download = `documented_code.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><WandSparkles size={21}/></div><div><b>DocuPilot<span> AI</span></b><small>CODE DOCUMENTATION AGENT</small></div></div>
      <div className="top-status"><span className={`status-dot ${health}`}></span> API {health}<span className="pill">HACKATHON BUILD</span></div>
    </header>
    <main className="main">
      <section className="hero">
        <div className="eyebrow"><Sparkles size={14}/> YOUR CODE, CLEARER</div>
        <h1>Documentation that<br/><span>understands your code.</span></h1>
        <p>Parse the structure. Generate meaningful docs. Review every change. Keep the developer in control.</p>
        <div className="hero-points"><span><CheckCircle2 size={15}/> 14 Languages supported</span><span><CheckCircle2 size={15}/> Human approval</span><span><CheckCircle2 size={15}/> Verifiable checks</span></div>
      </section>

      <section className="workspace">
        <div className="panel source-panel">
          <div className="panel-head"><div className="panel-title"><FileCode2 size={17}/> <span>01 / SOURCE CODE</span></div><span className="mini-tag">INPUT</span></div>
          <div className="toolbar">
            <select value={language} onChange={e=>changeLanguage(e.target.value)} aria-label="Programming language">
              {LANGUAGES.map(l => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </select>
            <button className="text-button" onClick={()=>setSource(SAMPLES[language] || SAMPLES.python)}><RefreshCw size={13}/> Load sample</button>
          </div>
          <textarea className="code-editor" spellCheck={false} value={source} onChange={e=>setSource(e.target.value)} aria-label="Source code" />
          <button className="primary-button" disabled={loading || source.trim().length<3} onClick={generate}>{loading?<LoaderCircle className="spin" size={17}/>:<Play size={16}/>} {loading?"Analyzing code...":"Analyze & generate"} <span>↗</span></button>
          <p className="hint">Your code is sent to the configured backend. Avoid pasting secrets or private code without permission.</p>
        </div>

        <div className="panel result-panel">
          <div className="panel-head"><div className="panel-title"><Bot size={18}/> <span>02 / AGENT WORKSPACE</span></div><span className={`mini-tag ${generated?"ready":""}`}>{generated?"REVIEW READY":"AWAITING INPUT"}</span></div>
          {!generated ? <div className="empty-state"><div className="empty-icon"><WandSparkles size={28}/></div><h3>Your documentation preview</h3><p>Run the agent to parse your code and generate a reviewable proposal.</p><div className="step-list"><span><i>1</i> Parse syntax and symbols</span><span><i>2</i> Generate documentation</span><span><i>3</i> Review before applying</span></div></div> :
          <>
            <div className="analysis-strip"><div><small>LANGUAGE</small><b>{generated.language}</b></div><div><small>SYMBOLS FOUND</small><b>{generated.analysis?.symbols?.length ?? 0}</b></div><div><small>ENGINE</small><b>{generated.mode === "openai" ? "DocuPilot (Cloud)" : "DocuPilot (Local Engine)"}</b></div></div>
            {generated.warning && <div className="notice" style={{ borderLeftColor: "#eab308", background: "rgba(234, 179, 8, 0.1)", color: "#fef08a" }}>⚡ {generated.warning}</div>}
            <div className="symbol-list">{(generated.analysis?.symbols || []).slice(0,5).map((s:any,i:number)=><span key={i} className="symbol"><Code2 size={12}/>{s.name}</span>)}</div>
            <label className="editor-label" htmlFor="proposed">PROPOSED CODE <span>Editable before approval</span></label>
            <textarea id="proposed" className="code-editor output-editor" spellCheck={false} value={edited} onChange={e=>setEdited(e.target.value)} />
            <div className="action-row"><button className="secondary-button" onClick={()=>{setGenerated(null);setVerification(null);setMessage("Proposal rejected. Original source remains unchanged.");}}><X size={15}/> Reject</button><button className="approve-button" disabled={approving || !edited.trim()} onClick={approve}>{approving?<LoaderCircle className="spin" size={16}/>:<Check size={16}/>} Approve & verify</button></div>
            {verification && <div className={`verification ${verification.passed?"pass":"fail"}`}><div className="verification-title"><ShieldCheck size={17}/>{verification.passed?"Checks passed":"Checks need attention"}</div>{verification.checks.map((c,i)=><div className="check-row" key={i}><span>{c.passed?"✓":"!"} {c.name}</span><small>{c.details}</small></div>)}<p>{verification.note}</p><button className="download-button" onClick={download}><ArrowDownToLine size={15}/> Download approved code</button></div>}
          </>}
          {message && <div className="notice">{message}</div>}
        </div>
      </section>

      <section className="bottom-grid">
        <div className="info-card"><div className="card-icon"><Activity size={19}/></div><div><h3>Evidence over guesswork</h3><p>Parser output, approval state and verification results are recorded for each run.</p></div></div>
        <div className="info-card"><div className="card-icon"><ShieldCheck size={19}/></div><div><h3>Developer stays in control</h3><p>The agent proposes changes. It never overwrites a source file automatically.</p></div></div>
      </section>
      <section className="history-panel">
        <div className="panel-head"><div className="panel-title"><History size={17}/> <span>RECENT RUNS</span></div><button className="text-button" onClick={refreshHistory}><RefreshCw size={13}/> Refresh</button></div>
        {history.length===0 ? <p className="history-empty">Your run history will appear here after the first analysis.</p> : <div className="history-list">{history.map(item=><div className="history-item" key={item.id}><span className="history-language">{item.language}</span><span className="history-id">{item.id.slice(0,8)}</span><span className={`history-status ${item.status.includes("verified")?"ok":""}`}>{item.status.replaceAll("_"," ")}</span><time>{new Date(item.created_at).toLocaleString()}</time></div>)}</div>}
      </section>
      <footer><span>DOCUPILOT AI · PROMPT PIONEERS</span><span>AI-generated code should always be reviewed.</span></footer>
    </main>
  </div>;
}
