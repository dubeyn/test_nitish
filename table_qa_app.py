"""
Table Question Answering App
Uses HuggingFace Transformers `table-question-answering` pipeline (TAPAS model)
to answer natural-language questions over any CSV / Excel file.
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd


# ---------------------------------------------------------------------------
# Lazy-load the HuggingFace pipeline so the UI opens instantly
# ---------------------------------------------------------------------------
_pipeline_cache: dict = {}


def _get_pipeline():
    if "tqa" not in _pipeline_cache:
        from transformers import pipeline  # heavy import; done once in background
        _pipeline_cache["tqa"] = pipeline(
            "table-question-answering",
            model="google/tapas-base-finetuned-wtq",
        )
    return _pipeline_cache["tqa"]


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------
class TableQAApp:
    MAX_ROWS = 100  # TAPAS works best with ≤100 rows; warn above this

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Table Q&A — HuggingFace TAPAS")
        self.root.geometry("1200x820")
        self.root.configure(bg="#f0f4f8")

        self.df: pd.DataFrame | None = None
        self.style = ttk.Style()
        self._setup_styles()
        self._build_ui()

        # Pre-warm the model in background so first question is fast
        threading.Thread(target=_get_pipeline, daemon=True).start()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------
    def _setup_styles(self) -> None:
        self.style.theme_use("clam")
        BG = "#f0f4f8"
        CARD = "#ffffff"
        ACCENT = "#2563eb"
        ACCENT_DARK = "#1d4ed8"

        self.style.configure("App.TFrame", background=BG)
        self.style.configure("Card.TLabelframe", background=CARD, borderwidth=1, relief="solid")
        self.style.configure(
            "Card.TLabelframe.Label",
            background=CARD,
            foreground="#1e293b",
            font=("Segoe UI", 10, "bold"),
        )
        self.style.configure(
            "Title.TLabel",
            background=BG,
            foreground="#0f172a",
            font=("Segoe UI", 20, "bold"),
        )
        self.style.configure(
            "Sub.TLabel",
            background=BG,
            foreground="#475569",
            font=("Segoe UI", 10),
        )
        self.style.configure(
            "TLabel",
            background=BG,
            foreground="#1e293b",
            font=("Segoe UI", 10),
        )
        self.style.configure(
            "Status.TLabel",
            background=CARD,
            foreground="#334155",
            font=("Segoe UI", 9, "italic"),
        )
        self.style.configure(
            "Accent.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(12, 7),
            background=ACCENT,
            foreground="#ffffff",
        )
        self.style.map(
            "Accent.TButton",
            background=[("active", ACCENT_DARK), ("pressed", "#1e3a8a"), ("disabled", "#94a3b8")],
            foreground=[("active", "#ffffff"), ("disabled", "#ffffff")],
        )
        self.style.configure(
            "Treeview",
            rowheight=24,
            font=("Segoe UI", 9),
            fieldbackground=CARD,
            background=CARD,
        )
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    # ------------------------------------------------------------------
    # UI Layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Header
        header = ttk.Frame(self.root, style="App.TFrame", padding=(18, 14, 18, 6))
        header.pack(fill="x")
        ttk.Label(header, text="Table Question Answering", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Load a CSV or Excel file and ask natural-language questions — powered by HuggingFace TAPAS.",
            style="Sub.TLabel",
        ).pack(anchor="w")

        # ── File section ─────────────────────────────────────────────
        file_frame = ttk.LabelFrame(
            self.root, text="1 · Load Data File", padding=12, style="Card.TLabelframe"
        )
        file_frame.pack(fill="x", padx=14, pady=(10, 6))

        self.file_var = tk.StringVar(value="No file selected")
        ttk.Button(
            file_frame,
            text="📂  Browse CSV / Excel",
            style="Accent.TButton",
            command=self.select_file,
        ).pack(side="left")
        ttk.Label(file_frame, textvariable=self.file_var).pack(side="left", padx=12)

        # ── Data preview ─────────────────────────────────────────────
        preview_frame = ttk.LabelFrame(
            self.root, text="2 · Data Preview (first 100 rows used for Q&A)", padding=8, style="Card.TLabelframe"
        )
        preview_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        self.tree = ttk.Treeview(preview_frame, show="headings")
        ys = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        # ── Question section ─────────────────────────────────────────
        qa_frame = ttk.LabelFrame(
            self.root, text="3 · Ask a Question", padding=12, style="Card.TLabelframe"
        )
        qa_frame.pack(fill="x", padx=14, pady=(0, 6))

        self.question_var = tk.StringVar()
        q_entry = ttk.Entry(
            qa_frame,
            textvariable=self.question_var,
            font=("Segoe UI", 11),
            width=80,
        )
        q_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        q_entry.bind("<Return>", lambda _: self.ask_question())

        self.ask_btn = ttk.Button(
            qa_frame,
            text="🔍  Ask",
            style="Accent.TButton",
            command=self.ask_question,
        )
        self.ask_btn.pack(side="left")

        # ── Answer section ────────────────────────────────────────────
        ans_frame = ttk.LabelFrame(
            self.root, text="4 · Answer", padding=12, style="Card.TLabelframe"
        )
        ans_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        self.answer_text = tk.Text(
            ans_frame,
            height=8,
            wrap="word",
            bg="#ffffff",
            fg="#0f172a",
            insertbackground="#0f172a",
            relief="solid",
            bd=1,
            font=("Consolas", 11),
            state="disabled",
        )
        self.answer_text.pack(fill="both", expand=True)

        # ── History section ───────────────────────────────────────────
        hist_frame = ttk.LabelFrame(
            self.root, text="5 · Q&A History", padding=8, style="Card.TLabelframe"
        )
        hist_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self.history_list = tk.Listbox(
            hist_frame,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#1e293b",
            selectbackground="#dbeafe",
            selectforeground="#1e3a8a",
            relief="flat",
            bd=0,
            activestyle="none",
        )
        h_scroll = ttk.Scrollbar(hist_frame, orient="vertical", command=self.history_list.yview)
        self.history_list.configure(yscrollcommand=h_scroll.set)
        self.history_list.pack(side="left", fill="both", expand=True)
        h_scroll.pack(side="right", fill="y")
        self.history_list.bind("<<ListboxSelect>>", self._restore_history_item)

        # ── Status bar ────────────────────────────────────────────────
        status_bar = ttk.Frame(self.root, style="App.TFrame", padding=(14, 4))
        status_bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready — load a file to get started.")
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        # Internal history store: list of (question, answer)
        self._history: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # File Loading
    # ------------------------------------------------------------------
    def select_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select CSV or Excel File",
            filetypes=[
                ("CSV Files", "*.csv"),
                ("Excel Files", "*.xlsx *.xls"),
                ("All Files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            if path.lower().endswith((".xlsx", ".xls")):
                self.df = pd.read_excel(path)
            else:
                self.df = pd.read_csv(path, encoding="unicode_escape")

            # TAPAS needs plain Python strings — strip whitespace from column names
            self.df.columns = [str(c).strip() for c in self.df.columns]
            # fillna before converting so NaN doesn't become literal "nan"
            self.df = self.df.fillna("").astype(str)

            self.file_var.set(path)
            self._load_preview(self.df)
            

            rows, cols = self.df.shape
            self.status_var.set(
                f"Loaded {rows} rows × {cols} columns.  "
                + ("Using all rows." if rows <= self.MAX_ROWS
                   else f"⚠ Only first {self.MAX_ROWS} rows will be used for Q&A (TAPAS limit).")
            )
        except Exception as exc:
            messagebox.showerror("File Error", f"Could not read file:\n{exc}")
            self.status_var.set("Failed to load file.")

    def _load_preview(self, df: pd.DataFrame) -> None:
        self.tree.delete(*self.tree.get_children())
        cols = list(df.columns)
        self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=130, stretch=True)
        for _, row in df.head(self.MAX_ROWS).iterrows():
            self.tree.insert("", "end", values=list(row))

    # ------------------------------------------------------------------
    # Q&A
    # ------------------------------------------------------------------
    def ask_question(self) -> None:
        if self.df is None:
            messagebox.showwarning("No Data", "Please load a CSV or Excel file first.")
            return

        question = self.question_var.get().strip()
        if not question:
            messagebox.showwarning("Empty Question", "Please type a question.")
            return

        self.ask_btn.configure(state="disabled")
        self.status_var.set("Thinking …")
        self._set_answer("⏳  Running model, please wait …")

        threading.Thread(
            target=self._run_qa,
            args=(question,),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Pandas query router — handles questions TAPAS cannot answer
    # ------------------------------------------------------------------
    def _pandas_answer(self, question: str) -> str | None:
        """
        Try to answer the question directly with pandas.
        Returns an answer string, or None if this method can't handle it
        (letting TAPAS take over).
        """
        q = question.lower().strip()
        df = self.df

        # ── Resolve which column the user is referring to ──────────────
        def _find_col(text: str) -> str | None:
            for col in df.columns:
                if col.lower() in text:
                    return col
            return None

        # ── Unique / distinct / list values ────────────────────────────
        if any(kw in q for kw in ("unique", "distinct", "different", "list of", "all values", "list all")):
            col = _find_col(q)
            if col:
                vals = df[col].dropna().unique().tolist()
                lines = "\n".join(f"  • {v}" for v in sorted(set(str(v) for v in vals)))
                return f"Unique values in '{col}' ({len(vals)} total):\n{lines}"
            # No specific column found — list all columns
            return "Columns in the dataset:\n" + "\n".join(f"  • {c}" for c in df.columns)

        # ── Column names / headers ──────────────────────────────────────
        if any(kw in q for kw in ("column", "columns", "headers", "fields")):
            return "Columns:\n" + "\n".join(f"  • {c}" for c in df.columns)

        # ── Row / record count ──────────────────────────────────────────
        if any(kw in q for kw in ("how many rows", "row count", "total rows", "number of rows", "how many records")):
            return f"Total rows: {len(df)}"

        # ── Missing / null values ───────────────────────────────────────
        if any(kw in q for kw in ("missing", "null", "nan", "empty", "blank")):
            col = _find_col(q)
            if col:
                n = df[col].replace("", pd.NA).isna().sum()
                return f"Missing values in '{col}': {n}"
            summary = df.replace("", pd.NA).isna().sum()
            lines = "\n".join(f"  {c}: {v}" for c, v in summary.items() if v > 0)
            return f"Missing values per column:\n{lines}" if lines else "No missing values found."

        # ── Value counts / frequency ────────────────────────────────────
        if any(kw in q for kw in ("count of", "frequency", "how many", "occurrences", "value count")):
            col = _find_col(q)
            if col:
                vc = df[col].value_counts().head(20)
                lines = "\n".join(f"  {k}: {v}" for k, v in vc.items())
                return f"Value counts for '{col}':\n{lines}"

        # ── Max / min for a column ──────────────────────────────────────
        if any(kw in q for kw in ("maximum", "highest", "largest", "max")):
            col = _find_col(q)
            if col:
                try:
                    val = pd.to_numeric(df[col], errors="coerce").max()
                    return f"Maximum value in '{col}': {val}"
                except Exception:
                    return f"Maximum value in '{col}': {df[col].max()}"

        if any(kw in q for kw in ("minimum", "lowest", "smallest", "min")):
            col = _find_col(q)
            if col:
                try:
                    val = pd.to_numeric(df[col], errors="coerce").min()
                    return f"Minimum value in '{col}': {val}"
                except Exception:
                    return f"Minimum value in '{col}': {df[col].min()}"

        # ── Average / mean ──────────────────────────────────────────────
        if any(kw in q for kw in ("average", "mean", "avg")):
            col = _find_col(q)
            if col:
                try:
                    val = pd.to_numeric(df[col], errors="coerce").mean()
                    return f"Average of '{col}': {val:.4f}"
                except Exception:
                    pass

        # ── Sum ─────────────────────────────────────────────────────────
        if "sum" in q or "total" in q:
            col = _find_col(q)
            if col:
                try:
                    val = pd.to_numeric(df[col], errors="coerce").sum()
                    return f"Sum of '{col}': {val}"
                except Exception:
                    pass

        # ── Show first N rows ───────────────────────────────────────────
        if any(kw in q for kw in ("first", "top", "head", "sample")):
            import re
            m = re.search(r"\d+", q)
            n = int(m.group()) if m else 5
            return df.head(n).to_string(index=False)

        return None  # let TAPAS handle it

    def _run_qa(self, question: str) -> None:
        try:
            # First try pandas-based routing (handles unique, list, counts etc.)
            pandas_result = self._pandas_answer(question)
            if pandas_result is not None:
                self.root.after(0, self._show_answer, question, pandas_result)
                return

            # Fall back to TAPAS for aggregation/lookup questions
            tqa = _get_pipeline()
            # TAPAS pipeline requires dict[str, list[str]] with plain Python strings.
            # Passing a DataFrame directly causes "len() of unsized object" on numpy dtypes.
            raw = self.df.head(self.MAX_ROWS)
            table = {str(col): [str(v) for v in raw[col].tolist()] for col in raw.columns}
            result = tqa(table=table, query=question)

            answer = result.get("answer", "")
            agg = result.get("aggregator", "")
            cells = result.get("cells", [])

            display = f"Answer:  {answer}"
            if agg and agg.upper() not in ("NONE", ""):
                display += f"\nAggregation:  {agg}"
            if cells:
                display += f"\nSource cells:  {', '.join(str(c) for c in cells)}"

            self.root.after(0, self._show_answer, question, display)
        except Exception as exc:
            self.root.after(0, self._show_answer, question, f"Error: {exc}")

    def _show_answer(self, question: str, answer: str) -> None:
        self._set_answer(answer)
        self.ask_btn.configure(state="normal")
        self.status_var.set("Done.")

        # Store in history
        self._history.append((question, answer))
        self.history_list.insert("end", f"Q: {question}")

    def _set_answer(self, text: str) -> None:
        self.answer_text.configure(state="normal")
        self.answer_text.delete("1.0", "end")
        self.answer_text.insert("1.0", text)
        self.answer_text.configure(state="disabled")

    def _restore_history_item(self, _event=None) -> None:
        sel = self.history_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._history):
            q, a = self._history[idx]
            self.question_var.set(q)
            self._set_answer(a)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    root = tk.Tk()
    TableQAApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
