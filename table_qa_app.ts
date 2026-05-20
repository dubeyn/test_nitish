/**
 * table_qa_app.ts
 *
 * Table Question Answering — TypeScript / Node.js + Express
 *
 * Features:
 *  - Upload CSV or Excel files
 *  - Smart pandas-style query router (unique, count, sum, avg, filter …)
 *  - OpenAI GPT fallback for free-form questions
 *  - Data preview table
 *  - Q&A history
 *
 * Install dependencies:
 *   npm install express multer papaparse xlsx openai
 *   npm install --save-dev typescript ts-node @types/express @types/multer @types/papaparse @types/node
 *
 * Run:
 *   npx ts-node table_qa_app.ts
 *   Then open http://localhost:3000
 */

import express, { Request, Response } from "express";
import multer from "multer";
import Papa from "papaparse";
import * as XLSX from "xlsx";
import OpenAI from "openai";
import * as fs from "fs";
import * as path from "path";
import * as http from "http";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Row = Record<string, string>;
type Table = Row[];

interface AskBody {
  question: string;
  openaiKey?: string;
}

// ---------------------------------------------------------------------------
// In-memory dataset store (single file for simplicity)
// ---------------------------------------------------------------------------
let currentTable: Table = [];
let currentColumns: string[] = [];
let currentFileName = "";

// ---------------------------------------------------------------------------
// Smart Query Router (mirrors Python _pandas_answer)
// ---------------------------------------------------------------------------
function findColumn(q: string, columns: string[]): string | undefined {
  const lower = q.toLowerCase();
  return columns.find((c) => lower.includes(c.toLowerCase()));
}

function queryRouter(question: string, table: Table, columns: string[]): string | null {
  const q = question.toLowerCase().trim();

  const unique = (col: string): string => {
    const vals = [...new Set(table.map((r) => r[col]).filter((v) => v !== "" && v != null))];
    vals.sort();
    const lines = vals.map((v) => `  • ${v}`).join("\n");
    return `Unique values in "${col}" (${vals.length} total):\n${lines}`;
  };

  const numericVals = (col: string): number[] =>
    table.map((r) => parseFloat(r[col])).filter((n) => !isNaN(n));

  // ── Columns / headers ─────────────────────────────────────────────────────
  if (/column|columns|headers?|fields?/.test(q)) {
    return "Columns in the dataset:\n" + columns.map((c) => `  • ${c}`).join("\n");
  }

  // ── Row count ──────────────────────────────────────────────────────────────
  if (/how many rows|row count|total rows|number of rows|how many records/.test(q)) {
    return `Total rows: ${table.length}`;
  }

  // ── Unique / distinct ──────────────────────────────────────────────────────
  if (/unique|distinct|different|list of|all values|list all/.test(q)) {
    const col = findColumn(q, columns);
    if (col) return unique(col);
    return "Columns in the dataset:\n" + columns.map((c) => `  • ${c}`).join("\n");
  }

  // ── Missing / null values ──────────────────────────────────────────────────
  if (/missing|null|empty|blank/.test(q)) {
    const col = findColumn(q, columns);
    if (col) {
      const n = table.filter((r) => r[col] === "" || r[col] == null).length;
      return `Missing values in "${col}": ${n}`;
    }
    const summary = columns
      .map((c) => ({ col: c, missing: table.filter((r) => r[c] === "" || r[c] == null).length }))
      .filter((x) => x.missing > 0)
      .map((x) => `  ${x.col}: ${x.missing}`)
      .join("\n");
    return summary ? `Missing values per column:\n${summary}` : "No missing values found.";
  }

  // ── Value counts / frequency ───────────────────────────────────────────────
  if (/count of|frequency|occurrences|value count|how many/.test(q)) {
    const col = findColumn(q, columns);
    if (col) {
      const counts: Record<string, number> = {};
      table.forEach((r) => {
        const v = r[col] ?? "(empty)";
        counts[v] = (counts[v] ?? 0) + 1;
      });
      const sorted = Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 20)
        .map(([k, v]) => `  ${k}: ${v}`)
        .join("\n");
      return `Value counts for "${col}":\n${sorted}`;
    }
  }

  // ── Max ────────────────────────────────────────────────────────────────────
  if (/maximum|highest|largest|\bmax\b/.test(q)) {
    const col = findColumn(q, columns);
    if (col) {
      const nums = numericVals(col);
      if (nums.length) return `Maximum value in "${col}": ${Math.max(...nums)}`;
      const max = [...table.map((r) => r[col])].sort().at(-1);
      return `Maximum value in "${col}": ${max}`;
    }
  }

  // ── Min ────────────────────────────────────────────────────────────────────
  if (/minimum|lowest|smallest|\bmin\b/.test(q)) {
    const col = findColumn(q, columns);
    if (col) {
      const nums = numericVals(col);
      if (nums.length) return `Minimum value in "${col}": ${Math.min(...nums)}`;
      const min = [...table.map((r) => r[col])].sort().at(0);
      return `Minimum value in "${col}": ${min}`;
    }
  }

  // ── Average / mean ─────────────────────────────────────────────────────────
  if (/average|mean|\bavg\b/.test(q)) {
    const col = findColumn(q, columns);
    if (col) {
      const nums = numericVals(col);
      if (nums.length) {
        const avg = nums.reduce((a, b) => a + b, 0) / nums.length;
        return `Average of "${col}": ${avg.toFixed(4)}`;
      }
    }
  }

  // ── Sum / total ────────────────────────────────────────────────────────────
  if (/\bsum\b|total/.test(q)) {
    const col = findColumn(q, columns);
    if (col) {
      const nums = numericVals(col);
      if (nums.length) return `Sum of "${col}": ${nums.reduce((a, b) => a + b, 0)}`;
    }
  }

  // ── Filter / where ─────────────────────────────────────────────────────────
  if (/where|filter|whose|with|having/.test(q)) {
    const col = findColumn(q, columns);
    if (col) {
      // Extract a value to filter by: everything after "is", "=", "equals", ":"
      const m = question.match(/(?:is|=|equals?|:)\s*["']?([^"'\s?]+)["']?/i);
      if (m) {
        const filterVal = m[1].toLowerCase();
        const filtered = table.filter((r) => r[col]?.toLowerCase().includes(filterVal));
        if (filtered.length === 0) return `No rows found where "${col}" matches "${m[1]}".`;
        const preview = filtered
          .slice(0, 10)
          .map((r, i) => `Row ${i + 1}: ${columns.map((c) => `${c}=${r[c]}`).join(", ")}`)
          .join("\n");
        return `${filtered.length} row(s) where "${col}" contains "${m[1]}":\n${preview}${filtered.length > 10 ? `\n… and ${filtered.length - 10} more.` : ""}`;
      }
    }
  }

  // ── Show / head / top ──────────────────────────────────────────────────────
  if (/^(show|display|give|top|first|head|sample)/.test(q)) {
    const m = q.match(/\d+/);
    const n = m ? Math.min(parseInt(m[0]), 50) : 5;
    const rows = table.slice(0, n);
    const lines = rows.map(
      (r, i) => `Row ${i + 1}: ` + columns.map((c) => `${c}=${r[c]}`).join(", ")
    );
    return `First ${n} rows:\n${lines.join("\n")}`;
  }

  return null; // let OpenAI handle it
}

// ---------------------------------------------------------------------------
// OpenAI fallback
// ---------------------------------------------------------------------------
async function openAIAnswer(
  question: string,
  table: Table,
  columns: string[],
  apiKey: string
): Promise<string> {
  const client = new OpenAI({ apiKey });

  const sample = table
    .slice(0, 30)
    .map((r) => columns.map((c) => r[c]).join(", "))
    .join("\n");

  const context =
    `Dataset info:\nRows: ${table.length}\nColumns: ${columns.join(", ")}\n\n` +
    `CSV sample (first 30 rows):\n${columns.join(",")}\n${sample}`;

  const response = await client.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [
      { role: "system", content: "You are a precise data analyst. Answer based only on the provided dataset." },
      { role: "user", content: `${context}\n\nQuestion: ${question}` },
    ],
    temperature: 0.2,
  });

  return response.choices[0].message.content ?? "No response from model.";
}

// ---------------------------------------------------------------------------
// Express setup
// ---------------------------------------------------------------------------
const app = express();
const upload = multer({ dest: "uploads/" });
app.use(express.json());

// ── POST /upload ─────────────────────────────────────────────────────────────
app.post("/upload", upload.single("file"), (req: Request, res: Response) => {
  if (!req.file) {
    res.status(400).json({ error: "No file uploaded." });
    return;
  }

  const filePath = req.file.path;
  const originalName = req.file.originalname.toLowerCase();

  try {
    let rows: Row[] = [];

    if (originalName.endsWith(".xlsx") || originalName.endsWith(".xls")) {
      const wb = XLSX.readFile(filePath);
      const sheet = wb.Sheets[wb.SheetNames[0]];
      rows = XLSX.utils.sheet_to_json<Row>(sheet, { defval: "" }).map((r) => {
        const clean: Row = {};
        for (const k of Object.keys(r)) clean[String(k).trim()] = String(r[k]);
        return clean;
      });
    } else {
      const csv = fs.readFileSync(filePath, "utf-8");
      const parsed = Papa.parse<Row>(csv, { header: true, skipEmptyLines: true });
      rows = parsed.data.map((r) => {
        const clean: Row = {};
        for (const k of Object.keys(r)) clean[String(k).trim()] = String(r[k] ?? "");
        return clean;
      });
    }

    fs.unlinkSync(filePath); // clean up temp file

    if (rows.length === 0) {
      res.status(400).json({ error: "File is empty or could not be parsed." });
      return;
    }

    currentTable = rows;
    currentColumns = Object.keys(rows[0]);
    currentFileName = req.file.originalname;

    res.json({
      fileName: currentFileName,
      rows: rows.length,
      columns: currentColumns,
      preview: rows.slice(0, 100),
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({ error: `Failed to parse file: ${msg}` });
  }
});

// ── POST /ask ─────────────────────────────────────────────────────────────────
app.post("/ask", async (req: Request, res: Response) => {
  const { question, openaiKey } = req.body as AskBody;

  if (!question?.trim()) {
    res.status(400).json({ error: "Question is required." });
    return;
  }
  if (currentTable.length === 0) {
    res.status(400).json({ error: "No data loaded. Upload a file first." });
    return;
  }

  // 1. Smart query router
  const routerAnswer = queryRouter(question, currentTable, currentColumns);
  if (routerAnswer !== null) {
    res.json({ answer: routerAnswer, source: "query-router" });
    return;
  }

  // 2. OpenAI fallback
  if (!openaiKey?.trim()) {
    res.json({
      answer:
        "This question needs AI reasoning. Please enter your OpenAI API key to enable GPT answers.",
      source: "hint",
    });
    return;
  }

  try {
    const answer = await openAIAnswer(question, currentTable, currentColumns, openaiKey.trim());
    res.json({ answer, source: "openai" });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({ error: `OpenAI error: ${msg}` });
  }
});

// ── GET / — serve the embedded HTML UI ───────────────────────────────────────
const HTML_UI = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Table Q&A — TypeScript</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: "Segoe UI", Arial, sans-serif; background: #f0f4f8; color: #1e293b; }
    header { background: #1d4ed8; color: #fff; padding: 18px 24px; }
    header h1 { font-size: 22px; margin-bottom: 4px; }
    header p { font-size: 13px; opacity: .85; }
    main { max-width: 1200px; margin: 0 auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
    .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; }
    .card h2 { font-size: 13px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 12px; }
    .row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    label { font-size: 13px; font-weight: 600; color: #334155; }
    input[type=text], input[type=password] {
      border: 1px solid #cbd5e1; border-radius: 6px; padding: 7px 10px; font-size: 14px;
      outline: none; transition: border-color .2s;
    }
    input[type=text]:focus, input[type=password]:focus { border-color: #2563eb; }
    .btn {
      display: inline-flex; align-items: center; gap: 6px;
      background: #2563eb; color: #fff; border: none; border-radius: 6px;
      padding: 8px 16px; font-size: 14px; font-weight: 600; cursor: pointer;
      transition: background .15s;
    }
    .btn:hover { background: #1d4ed8; }
    .btn:disabled { background: #94a3b8; cursor: not-allowed; }
    .btn.green { background: #16a34a; } .btn.green:hover { background: #15803d; }
    .file-label {
      display: inline-flex; align-items: center; gap: 8px;
      background: #f1f5f9; border: 1px dashed #94a3b8; border-radius: 6px;
      padding: 8px 14px; cursor: pointer; font-size: 14px; color: #475569;
      transition: border-color .2s;
    }
    .file-label:hover { border-color: #2563eb; color: #2563eb; }
    #file-input { display: none; }
    #file-status { font-size: 13px; color: #475569; }
    #file-status.ok { color: #16a34a; font-weight: 600; }
    .table-wrap { overflow: auto; max-height: 260px; border: 1px solid #e2e8f0; border-radius: 6px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { background: #f8fafc; position: sticky; top: 0; z-index: 1; padding: 8px 12px;
         border-bottom: 1px solid #e2e8f0; text-align: left; font-weight: 700; white-space: nowrap; }
    td { padding: 6px 12px; border-bottom: 1px solid #f1f5f9; white-space: nowrap; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #f8fafc; }
    #question { flex: 1; min-width: 300px; }
    #answer-box {
      background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;
      padding: 14px; min-height: 80px; font-family: Consolas, monospace; font-size: 14px;
      white-space: pre-wrap; line-height: 1.6;
    }
    .badge { font-size: 11px; padding: 2px 8px; border-radius: 99px; font-weight: 600; }
    .badge.router { background: #dbeafe; color: #1e40af; }
    .badge.openai { background: #dcfce7; color: #166534; }
    .badge.hint { background: #fef9c3; color: #854d0e; }
    #history { list-style: none; max-height: 160px; overflow-y: auto; }
    #history li {
      padding: 7px 10px; border-radius: 6px; cursor: pointer; font-size: 13px;
      border-bottom: 1px solid #f1f5f9;
    }
    #history li:hover { background: #eff6ff; }
    #history li.active { background: #dbeafe; color: #1e3a8a; font-weight: 600; }
    .spinner { display: none; width: 18px; height: 18px; border: 3px solid #bfdbfe;
               border-top-color: #2563eb; border-radius: 50%; animation: spin .7s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .source-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
    #status-bar { background: #1e293b; color: #94a3b8; font-size: 12px; padding: 6px 24px; position: fixed; bottom: 0; left: 0; right: 0; }
  </style>
</head>
<body>

<header>
  <h1>📊 Table Question Answering</h1>
  <p>Upload CSV or Excel &amp; ask natural-language questions. Powered by smart query router + OpenAI GPT.</p>
</header>

<main>

  <!-- ① File Upload -->
  <div class="card">
    <h2>① Load Data File</h2>
    <div class="row">
      <label class="file-label" for="file-input">
        📂 Browse CSV / Excel
      </label>
      <input type="file" id="file-input" accept=".csv,.xlsx,.xls" />
      <span id="file-status">No file selected</span>
    </div>
  </div>

  <!-- ② OpenAI Key (optional) -->
  <div class="card">
    <h2>② OpenAI API Key (optional — for complex questions)</h2>
    <div class="row">
      <label for="api-key">API Key:</label>
      <input type="password" id="api-key" placeholder="sk-..." style="width:360px" />
    </div>
  </div>

  <!-- ③ Data Preview -->
  <div class="card" id="preview-card" style="display:none">
    <h2>③ Data Preview</h2>
    <div class="table-wrap" id="preview-table-wrap"></div>
  </div>

  <!-- ④ Ask Question -->
  <div class="card">
    <h2>④ Ask a Question</h2>
    <div class="row">
      <input type="text" id="question" placeholder="e.g. give unique Region list, total Sales, how many rows …" />
      <button class="btn" id="ask-btn" onclick="askQuestion()">🔍 Ask</button>
      <div class="spinner" id="spinner"></div>
    </div>
  </div>

  <!-- ⑤ Answer -->
  <div class="card">
    <h2>⑤ Answer</h2>
    <div class="source-row">
      <span style="font-size:13px;color:#64748b">Source:</span>
      <span class="badge" id="source-badge" style="display:none"></span>
    </div>
    <div id="answer-box">Answer will appear here after you ask a question.</div>
  </div>

  <!-- ⑥ History -->
  <div class="card">
    <h2>⑥ Q&amp;A History</h2>
    <ul id="history"></ul>
  </div>

</main>

<div id="status-bar">Ready — load a file to get started.</div>

<script>
  let history = [];
  let activeIdx = -1;

  document.getElementById('file-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setStatus('Uploading …');
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) { alert(data.error); setStatus('Upload failed.'); return; }
      const s = document.getElementById('file-status');
      s.textContent = data.fileName + ' — ' + data.rows + ' rows × ' + data.columns.length + ' columns';
      s.className = 'ok';
      renderPreview(data.columns, data.preview);
      setStatus('Loaded ' + data.rows + ' rows × ' + data.columns.length + ' columns.');
    } catch(err) { alert('Upload error: ' + err); setStatus('Upload error.'); }
  });

  function renderPreview(cols, rows) {
    const card = document.getElementById('preview-card');
    const wrap = document.getElementById('preview-table-wrap');
    const header = cols.map(c => '<th>' + esc(c) + '</th>').join('');
    const body = rows.map(r =>
      '<tr>' + cols.map(c => '<td>' + esc(r[c] ?? '') + '</td>').join('') + '</tr>'
    ).join('');
    wrap.innerHTML = '<table><thead><tr>' + header + '</tr></thead><tbody>' + body + '</tbody></table>';
    card.style.display = 'block';
  }

  document.getElementById('question').addEventListener('keydown', e => {
    if (e.key === 'Enter') askQuestion();
  });

  async function askQuestion() {
    const q = document.getElementById('question').value.trim();
    if (!q) return;
    const apiKey = document.getElementById('api-key').value.trim();

    document.getElementById('ask-btn').disabled = true;
    document.getElementById('spinner').style.display = 'block';
    document.getElementById('answer-box').textContent = '⏳ Thinking …';
    document.getElementById('source-badge').style.display = 'none';
    setStatus('Thinking …');

    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, openaiKey: apiKey }),
      });
      const data = await res.json();

      if (!res.ok) { document.getElementById('answer-box').textContent = 'Error: ' + data.error; }
      else {
        document.getElementById('answer-box').textContent = data.answer;
        const badge = document.getElementById('source-badge');
        badge.style.display = 'inline-block';
        badge.className = 'badge ' + (data.source || 'router');
        badge.textContent = data.source === 'openai' ? 'OpenAI GPT' :
                            data.source === 'hint'   ? 'Hint' : 'Smart Router';
        addHistory(q, data.answer, data.source);
        setStatus('Done.');
      }
    } catch(err) {
      document.getElementById('answer-box').textContent = 'Request failed: ' + err;
      setStatus('Error.');
    } finally {
      document.getElementById('ask-btn').disabled = false;
      document.getElementById('spinner').style.display = 'none';
    }
  }

  function addHistory(q, a, src) {
    history.push({ q, a, src });
    activeIdx = history.length - 1;
    renderHistory();
  }

  function renderHistory() {
    const ul = document.getElementById('history');
    ul.innerHTML = history.map((item, i) =>
      '<li class="' + (i === activeIdx ? 'active' : '') + '" onclick="restoreHistory(' + i + ')">Q: ' + esc(item.q) + '</li>'
    ).join('');
  }

  function restoreHistory(i) {
    activeIdx = i;
    const item = history[i];
    document.getElementById('question').value = item.q;
    document.getElementById('answer-box').textContent = item.a;
    const badge = document.getElementById('source-badge');
    badge.style.display = 'inline-block';
    badge.className = 'badge ' + item.src;
    badge.textContent = item.src === 'openai' ? 'OpenAI GPT' :
                        item.src === 'hint'   ? 'Hint' : 'Smart Router';
    renderHistory();
  }

  function setStatus(msg) {
    document.getElementById('status-bar').textContent = msg;
  }

  function esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
</script>

</body>
</html>`;

app.get("/", (_req: Request, res: Response) => {
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.send(HTML_UI);
});

// ---------------------------------------------------------------------------
// Start server
// ---------------------------------------------------------------------------
const PORT = 3000;
const server = http.createServer(app);

server.listen(PORT, () => {
  console.log(`\n  Table Q&A app running at  http://localhost:${PORT}\n`);
  // Auto-open browser on Windows / Mac / Linux
  const url = `http://localhost:${PORT}`;
  const opener =
    process.platform === "win32" ? "start" :
    process.platform === "darwin" ? "open" : "xdg-open";
  import("child_process").then(({ exec }) => exec(`${opener} ${url}`));
});
