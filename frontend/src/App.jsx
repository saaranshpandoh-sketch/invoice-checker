import { useEffect, useRef, useState } from "react";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.gif";
const MAX_FILE_MB = 4;
const MAX_FILES = 10;
const PW_KEY = "invoice-checker-password";

function loadPassword() {
  try {
    return sessionStorage.getItem(PW_KEY) || "";
  } catch {
    return "";
  }
}

function savePassword(pw) {
  try {
    if (pw) sessionStorage.setItem(PW_KEY, pw);
    else sessionStorage.removeItem(PW_KEY);
  } catch {
    /* storage unavailable - password just won't be remembered */
  }
}

const STATUS_LABEL = {
  ok: "Looks good",
  warnings: "Needs review",
  errors: "Problems found",
  not_invoice: "Not an invoice",
};

export default function App() {
  // null = still checking, false = no password needed, true = needs password
  const [needsPassword, setNeedsPassword] = useState(null);
  const [password, setPassword] = useState(loadPassword);
  const [unlocked, setUnlocked] = useState(false);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(async (h) => {
        setNeedsPassword(h.password_required);
        if (!h.password_required) return setUnlocked(true);
        const saved = loadPassword();
        if (saved && (await checkPassword(saved))) setUnlocked(true);
      })
      .catch(() => setNeedsPassword(false) || setUnlocked(true));
  }, []);

  let content;
  if (needsPassword === null) content = <div className="page muted">Loading…</div>;
  else if (!unlocked)
    content = (
      <PasswordGate
        onUnlock={(pw) => {
          savePassword(pw);
          setPassword(pw);
          setUnlocked(true);
        }}
      />
    );
  else
    content = (
      <Checker
        password={password}
        onLocked={() => {
          savePassword("");
          setUnlocked(false);
        }}
      />
    );

  return (
    <>
      {content}
      <Footer />
    </>
  );
}

function Footer() {
  return (
    <footer className="footer">
      Built by Saaransh ·{" "}
      <a href="https://github.com/saaranshpandoh-sketch/invoice-checker" target="_blank" rel="noreferrer">
        View on GitHub
      </a>
    </footer>
  );
}

async function checkPassword(pw) {
  const res = await fetch("/api/check-password", { method: "POST", headers: { "X-App-Password": pw } });
  return res.ok;
}

function PasswordGate({ onUnlock }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (await checkPassword(value)) onUnlock(value);
      else setError("Wrong password.");
    } catch {
      setError("Can't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header>
        <h1>Invoice Checker</h1>
        <p className="subtitle">This app is password protected.</p>
      </header>
      <form className="card login" onSubmit={submit}>
        <label htmlFor="pw">Password</label>
        <input id="pw" type="password" autoFocus value={value} onChange={(e) => setValue(e.target.value)} />
        <button className="primary" disabled={!value || busy}>
          {busy ? "Checking…" : "Unlock"}
        </button>
        {error && <div className="alert">{error}</div>}
      </form>
    </div>
  );
}

function Checker({ password, onLocked }) {
  const [files, setFiles] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  function addFiles(list) {
    const incoming = Array.from(list);
    const tooBig = incoming.filter((f) => f.size > MAX_FILE_MB * 1024 * 1024);
    setError(tooBig.length ? `Skipped (over ${MAX_FILE_MB} MB): ${tooBig.map((f) => f.name).join(", ")}` : "");
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name + f.size));
      const fresh = incoming.filter((f) => !tooBig.includes(f) && !names.has(f.name + f.size));
      return [...prev, ...fresh].slice(0, MAX_FILES);
    });
  }

  function removeFile(index) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function analyze() {
    setLoading(true);
    setError("");
    setResults([]);
    // One request per file: keeps each upload under Vercel's size limit,
    // runs them in parallel, and shows each result as soon as it's ready.
    async function analyzeOne(file) {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/analyze", {
        method: "POST",
        body: form,
        headers: { "X-App-Password": password },
      });
      if (res.status === 401) {
        onLocked();
        throw new Error("Wrong password.");
      }
      const body = await res.json().catch(() => null);
      const result = res.ok && body ? body : { filename: file.name, ok: false, error: body?.detail || `Server error (${res.status})` };
      setResults((prev) => [...prev, result]);
    }
    try {
      await Promise.all(files.map(analyzeOne));
    } catch (e) {
      setError(
        e.message === "Failed to fetch"
          ? "Can't reach the backend. Is the FastAPI server running on port 8000?"
          : e.message
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header>
        <h1>Invoice Checker</h1>
        <p className="subtitle">
          Upload invoices and AI will summarize them and flag anything that looks wrong.
        </p>
      </header>

      <div
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onClick={() => inputRef.current.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <div className="drop-icon">📄</div>
        <strong>Drop invoices here or click to browse</strong>
        <span className="muted">PDF, PNG, JPG, WEBP · up to {MAX_FILES} files, {MAX_FILE_MB} MB each</span>
      </div>

      {files.length > 0 && (
        <div className="file-list">
          {files.map((f, i) => (
            <div className="file-chip" key={f.name + f.size}>
              <span>{f.name}</span>
              <button aria-label={`Remove ${f.name}`} onClick={() => removeFile(i)} disabled={loading}>
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <button className="primary" onClick={analyze} disabled={!files.length || loading}>
        {loading ? (
          <>
            <span className="spinner" /> Analyzing {files.length} invoice{files.length > 1 ? "s" : ""}…
          </>
        ) : (
          "Analyze invoices"
        )}
      </button>

      {error && <div className="alert">{error}</div>}

      <div className="results">
        {results.map((r, i) => (
          <ResultCard key={i} result={r} />
        ))}
      </div>
    </div>
  );
}

function ResultCard({ result }) {
  if (!result.ok) {
    return (
      <section className="card">
        <div className="card-head">
          <h2>{result.filename}</h2>
          <span className="badge errors">Failed</span>
        </div>
        <p className="alert">{result.error}</p>
      </section>
    );
  }

  const inv = result.invoice;
  const money = (n) =>
    n == null ? "—" : `${inv.currency ? inv.currency + " " : ""}${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <section className="card">
      <div className="card-head">
        <h2>{result.filename}</h2>
        <span className={`badge ${result.status}`}>{STATUS_LABEL[result.status]}</span>
      </div>

      <p className="summary">{inv.summary}</p>

      {inv.is_invoice && (
        <>
          <div className="fields">
            <Field label="Vendor" value={inv.vendor_name} />
            <Field label="Customer" value={inv.customer_name} />
            <Field label="Invoice #" value={inv.invoice_number} />
            <Field label="Invoice date" value={inv.invoice_date} />
            <Field label="Due date" value={inv.due_date} />
            <Field label="Total" value={money(inv.total)} strong />
          </div>

          <h3>Issues ({result.issues.length})</h3>
          {result.issues.length === 0 ? (
            <p className="muted">No issues found. ✅</p>
          ) : (
            <ul className="issues">
              {result.issues.map((issue, i) => (
                <li key={i} className={`issue ${issue.severity}`}>
                  <span className="issue-icon">
                    {issue.severity === "error" ? "🔴" : issue.severity === "warning" ? "🟡" : "🔵"}
                  </span>
                  <div>
                    <strong>{issue.category}</strong>
                    <span className="source">{issue.source === "calculated" ? "math check" : "AI review"}</span>
                    <div>{issue.message}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {inv.line_items.length > 0 && (
            <details>
              <summary>Line items ({inv.line_items.length})</summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th className="num">Qty</th>
                      <th className="num">Unit price</th>
                      <th className="num">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inv.line_items.map((li, i) => (
                      <tr key={i}>
                        <td>{li.description}</td>
                        <td className="num">{li.quantity ?? "—"}</td>
                        <td className="num">{money(li.unit_price)}</td>
                        <td className="num">{money(li.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <TotalRow label="Subtotal" value={inv.subtotal} money={money} />
                    {inv.discount != null && <TotalRow label="Discount" value={inv.discount} money={money} />}
                    {inv.shipping != null && <TotalRow label="Shipping" value={inv.shipping} money={money} />}
                    <TotalRow label="Tax" value={inv.tax} money={money} />
                    <TotalRow label="Total" value={inv.total} money={money} />
                  </tfoot>
                </table>
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function Field({ label, value, strong }) {
  return (
    <div className="field">
      <span className="muted">{label}</span>
      <span className={strong ? "strong" : ""}>{value || <em className="missing">missing</em>}</span>
    </div>
  );
}

function TotalRow({ label, value, money }) {
  return (
    <tr>
      <td colSpan={3} className="num">{label}</td>
      <td className="num">{money(value)}</td>
    </tr>
  );
}
