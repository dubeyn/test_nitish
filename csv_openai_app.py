import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
from html import escape
from pathlib import Path

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import pandas as pd
from openai import OpenAI


class CsvOpenAIApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CSV + OpenAI Explorer")
        self.root.geometry("1200x760")
        self.root.configure(bg="#f3f6fb")

        self.df = None
        self.style = ttk.Style()
        self.icons = {}
        self._setup_styles()
        self._create_icons()
        self._build_ui()

    def _setup_styles(self) -> None:
        self.style.theme_use("clam")
        self.style.configure("App.TFrame", background="#f3f6fb")
        self.style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1, relief="solid")
        self.style.configure("Card.TLabelframe.Label", background="#ffffff", foreground="#1f2937", font=("Segoe UI", 10, "bold"))
        self.style.configure("Title.TLabel", background="#f3f6fb", foreground="#0f172a", font=("Segoe UI", 18, "bold"))
        self.style.configure("Subtitle.TLabel", background="#f3f6fb", foreground="#475569", font=("Segoe UI", 10))
        self.style.configure("Status.TLabel", background="#ffffff", foreground="#334155", font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabel", background="#f3f6fb", foreground="#1f2937", font=("Segoe UI", 10))
        self.style.configure("TEntry", padding=5)
        self.style.configure("TCombobox", padding=4)
        self.style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(10, 6), background="#1d4ed8", foreground="#ffffff")
        self.style.map(
            "Accent.TButton",
            background=[("active", "#1e40af"), ("pressed", "#1e3a8a")],
            foreground=[("active", "#ffffff")],
        )
        self.style.configure("Treeview", rowheight=24, font=("Segoe UI", 9), fieldbackground="#ffffff", background="#ffffff")
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _create_icon(self, kind: str) -> tk.PhotoImage:
        icon = tk.PhotoImage(width=16, height=16)
        icon.put("#ffffff", to=(0, 0, 16, 16))

        if kind == "csv":
            icon.put("#f59e0b", to=(1, 4, 15, 15))
            icon.put("#fbbf24", to=(3, 1, 9, 5))
            icon.put("#ffffff", to=(3, 7, 13, 8))
            icon.put("#ffffff", to=(3, 10, 12, 11))
        elif kind == "analyze":
            icon.put("#1d4ed8", to=(1, 1, 15, 15))
            icon.put("#93c5fd", to=(3, 9, 5, 13))
            icon.put("#93c5fd", to=(7, 6, 9, 13))
            icon.put("#93c5fd", to=(11, 4, 13, 13))
        elif kind == "graph":
            icon.put("#0ea5e9", to=(1, 1, 15, 15))
            icon.put("#ffffff", to=(3, 12, 5, 14))
            icon.put("#ffffff", to=(6, 8, 8, 10))
            icon.put("#ffffff", to=(9, 5, 11, 7))
            icon.put("#ffffff", to=(12, 3, 14, 5))
        elif kind == "report":
            icon.put("#16a34a", to=(1, 1, 15, 15))
            icon.put("#ffffff", to=(4, 4, 12, 5))
            icon.put("#ffffff", to=(4, 7, 12, 8))
            icon.put("#ffffff", to=(4, 10, 9, 11))
            icon.put("#bbf7d0", to=(10, 10, 13, 13))
        return icon

    def _create_icons(self) -> None:
        self.icons["csv"] = self._create_icon("csv")
        self.icons["analyze"] = self._create_icon("analyze")
        self.icons["graph"] = self._create_icon("graph")
        self.icons["report"] = self._create_icon("report")

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, style="App.TFrame", padding=(16, 14, 16, 6))
        header.pack(fill="x")
        ttk.Label(header, text="CSV + OpenAI Data Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Upload CSV files, ask AI questions, and generate visual charts in one place.",
            style="Subtitle.TLabel",
        ).pack(anchor="w")

        top = ttk.Frame(self.root, style="App.TFrame", padding=(12, 6, 12, 6))
        top.pack(fill="x")

        ttk.Label(top, text="OpenAI API Key:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        self.api_key_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.api_key_var, show="*", width=48).grid(
            row=0, column=1, sticky="we", pady=4
        )

        ttk.Label(top, text="Model:").grid(row=0, column=2, sticky="w", padx=(12, 6), pady=4)
        self.model_var = tk.StringVar(value="gpt-4o-mini")
        ttk.Entry(top, textvariable=self.model_var, width=20).grid(row=0, column=3, sticky="w", pady=4)

        self.file_var = tk.StringVar(value="No CSV selected")
        self.select_btn = ttk.Button(
            top,
            text=" Select CSV",
            image=self.icons["csv"],
            compound="left",
            style="Accent.TButton",
            command=self.select_csv,
        )
        self.select_btn.grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(top, textvariable=self.file_var).grid(row=1, column=1, columnspan=3, sticky="w", pady=4)

        top.columnconfigure(1, weight=1)

        prompt_frame = ttk.LabelFrame(self.root, text="Ask OpenAI About This CSV", padding=12, style="Card.TLabelframe")
        prompt_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.prompt_text = tk.Text(
            prompt_frame,
            height=5,
            wrap="word",
            bg="#ffffff",
            fg="#0f172a",
            insertbackground="#0f172a",
            relief="solid",
            bd=1,
            font=("Consolas", 10),
        )
        self.prompt_text.pack(fill="x")
        self.prompt_text.insert(
            "1.0",
            "Summarize this dataset and mention key trends, outliers, and useful business insights.",
        )

        btn_frame = ttk.Frame(prompt_frame)
        btn_frame.pack(fill="x", pady=(8, 0))
        self.run_btn = ttk.Button(
            btn_frame,
            text=" Analyze CSV",
            image=self.icons["analyze"],
            compound="left",
            style="Accent.TButton",
            command=self.analyze_csv,
        )
        self.run_btn.pack(side="left")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(btn_frame, textvariable=self.status_var, style="Status.TLabel").pack(side="left", padx=10)

        graph_frame = ttk.LabelFrame(self.root, text="Create Graph", padding=12, style="Card.TLabelframe")
        graph_frame.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Label(graph_frame, text="Chart Type:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        self.chart_type_var = tk.StringVar(value="Histogram")
        self.chart_type_combo = ttk.Combobox(
            graph_frame,
            textvariable=self.chart_type_var,
            values=["Histogram", "Bar", "Line", "Scatter"],
            state="readonly",
            width=14,
        )
        self.chart_type_combo.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(graph_frame, text="X Column:").grid(row=0, column=2, sticky="w", padx=(12, 6), pady=4)
        self.x_col_var = tk.StringVar()
        self.x_col_combo = ttk.Combobox(graph_frame, textvariable=self.x_col_var, state="readonly", width=24)
        self.x_col_combo.grid(row=0, column=3, sticky="w", pady=4)

        ttk.Label(graph_frame, text="Y Column:").grid(row=0, column=4, sticky="w", padx=(12, 6), pady=4)
        self.y_col_var = tk.StringVar()
        self.y_col_combo = ttk.Combobox(graph_frame, textvariable=self.y_col_var, state="readonly", width=24)
        self.y_col_combo.grid(row=0, column=5, sticky="w", pady=4)

        self.graph_btn = ttk.Button(
            graph_frame,
            text=" Create Graph",
            image=self.icons["graph"],
            compound="left",
            style="Accent.TButton",
            command=self.create_graph,
        )
        self.graph_btn.grid(
            row=0, column=6, sticky="w", padx=(12, 0), pady=4
        )

        graph_frame.columnconfigure(7, weight=1)

        data_frame = ttk.LabelFrame(self.root, text="CSV Data (Preview)", padding=8, style="Card.TLabelframe")
        data_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.tree = ttk.Treeview(data_frame, show="headings")
        y_scroll = ttk.Scrollbar(data_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(data_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        data_frame.rowconfigure(0, weight=1)
        data_frame.columnconfigure(0, weight=1)

        output_frame = ttk.LabelFrame(self.root, text="OpenAI Output", padding=8, style="Card.TLabelframe")
        output_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        output_actions = ttk.Frame(output_frame)
        output_actions.pack(fill="x", pady=(0, 6))

        ttk.Label(output_actions, text="Report Format:").pack(side="left")
        self.report_format_var = tk.StringVar(value="TXT")
        self.report_format_combo = ttk.Combobox(
            output_actions,
            textvariable=self.report_format_var,
            values=["TXT", "HTML"],
            width=8,
            state="readonly",
        )
        self.report_format_combo.pack(side="left", padx=(6, 8))

        self.download_btn = ttk.Button(
            output_actions,
            text=" Download Report",
            image=self.icons["report"],
            compound="left",
            style="Accent.TButton",
            command=self.download_report,
        )
        self.download_btn.pack(side="left")

        self.output_text = tk.Text(
            output_frame,
            height=12,
            wrap="word",
            bg="#ffffff",
            fg="#0f172a",
            insertbackground="#0f172a",
            relief="solid",
            bd=1,
            font=("Consolas", 10),
        )
        self.output_text.pack(fill="both", expand=True)

    def select_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            self.df = pd.read_csv(path, encoding="unicode_escape")
            self.file_var.set(path)
            self._load_table_preview(self.df)
            self._update_graph_options(self.df)
            self.status_var.set(f"Loaded {len(self.df)} rows and {len(self.df.columns)} columns")
        except Exception as exc:
            messagebox.showerror("CSV Error", f"Failed to read CSV file:\n{exc}")
            self.status_var.set("Failed to load CSV")

    def _update_graph_options(self, df: pd.DataFrame) -> None:
        columns = [str(col) for col in df.columns]
        numeric_cols = [str(col) for col in df.select_dtypes(include="number").columns]

        self.x_col_combo["values"] = columns
        self.y_col_combo["values"] = [""] + numeric_cols

        if columns:
            self.x_col_var.set(columns[0])
        if numeric_cols:
            self.y_col_var.set(numeric_cols[0])
        else:
            self.y_col_var.set("")

    def _load_table_preview(self, df: pd.DataFrame) -> None:
        self.tree.delete(*self.tree.get_children())

        columns = [str(col) for col in df.columns]
        self.tree["columns"] = columns

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=140, stretch=True)

        preview = df.head(100).fillna("")
        for _, row in preview.iterrows():
            self.tree.insert("", "end", values=[str(v) for v in row.tolist()])

    def analyze_csv(self) -> None:
        if self.df is None:
            messagebox.showwarning("No CSV", "Please select a CSV file first.")
            return

        if not self.api_key_var.get().strip():
            messagebox.showwarning("Missing API Key", "Please enter your OpenAI API key.")
            return

        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("Missing Prompt", "Please add a question or prompt.")
            return

        self.run_btn.configure(state="disabled")
        self.status_var.set("Analyzing...")
        self.output_text.delete("1.0", "end")

        thread = threading.Thread(target=self._analyze_in_background, args=(prompt,), daemon=True)
        thread.start()

    def create_graph(self) -> None:
        if self.df is None:
            messagebox.showwarning("No CSV", "Please select a CSV file first.")
            return

        chart_type = self.chart_type_var.get().strip()
        x_col = self.x_col_var.get().strip()
        y_col = self.y_col_var.get().strip()

        if not x_col:
            messagebox.showwarning("Missing X Column", "Please choose an X column.")
            return

        try:
            fig = Figure(figsize=(8, 5), dpi=100)
            ax = fig.add_subplot(111)

            if chart_type == "Histogram":
                x_vals = pd.to_numeric(self.df[x_col], errors="coerce").dropna()
                if x_vals.empty:
                    raise ValueError("Histogram needs a numeric X column with valid values.")
                ax.hist(x_vals, bins=20)
                ax.set_title(f"Histogram of {x_col}")
                ax.set_xlabel(x_col)
                ax.set_ylabel("Frequency")

            elif chart_type == "Bar":
                if y_col:
                    y_vals = pd.to_numeric(self.df[y_col], errors="coerce")
                    grouped = (
                        pd.DataFrame({x_col: self.df[x_col], y_col: y_vals})
                        .dropna()
                        .groupby(x_col, as_index=False)[y_col]
                        .mean()
                        .head(20)
                    )
                    if grouped.empty:
                        raise ValueError("No valid rows available for bar chart.")
                    ax.bar(grouped[x_col].astype(str), grouped[y_col])
                    ax.set_ylabel(f"Average {y_col}")
                    ax.set_title(f"Bar Chart: {x_col} vs average {y_col}")
                else:
                    counts = self.df[x_col].astype(str).value_counts().head(20)
                    ax.bar(counts.index, counts.values)
                    ax.set_ylabel("Count")
                    ax.set_title(f"Bar Chart: {x_col} counts")

                ax.set_xlabel(x_col)
                ax.tick_params(axis="x", rotation=30)

            elif chart_type == "Line":
                if not y_col:
                    raise ValueError("Line chart needs a Y column.")
                x_vals = self.df[x_col]
                y_vals = pd.to_numeric(self.df[y_col], errors="coerce")
                plot_df = pd.DataFrame({x_col: x_vals, y_col: y_vals}).dropna()
                if plot_df.empty:
                    raise ValueError("No valid numeric values found for selected columns.")
                ax.plot(plot_df[x_col], plot_df[y_col])
                ax.set_title(f"Line Chart: {y_col} by {x_col}")
                ax.set_xlabel(x_col)
                ax.set_ylabel(y_col)
                ax.tick_params(axis="x", rotation=30)

            elif chart_type == "Scatter":
                if not y_col:
                    raise ValueError("Scatter chart needs a Y column.")
                x_vals = pd.to_numeric(self.df[x_col], errors="coerce")
                y_vals = pd.to_numeric(self.df[y_col], errors="coerce")
                plot_df = pd.DataFrame({x_col: x_vals, y_col: y_vals}).dropna()
                if plot_df.empty:
                    raise ValueError("Scatter needs numeric X and Y columns with valid values.")
                ax.scatter(plot_df[x_col], plot_df[y_col])
                ax.set_title(f"Scatter Plot: {x_col} vs {y_col}")
                ax.set_xlabel(x_col)
                ax.set_ylabel(y_col)

            else:
                raise ValueError("Unsupported chart type selected.")

            fig.tight_layout()
            self._show_chart_window(fig, f"{chart_type} Graph")
            self.status_var.set("Graph created")
        except Exception as exc:
            messagebox.showerror("Graph Error", str(exc))

    def _show_chart_window(self, fig: Figure, title: str) -> None:
        chart_window = tk.Toplevel(self.root)
        chart_window.title(title)
        chart_window.geometry("900x600")

        canvas = FigureCanvasTkAgg(fig, master=chart_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _analyze_in_background(self, user_prompt: str) -> None:
        try:
            client = OpenAI(api_key=self.api_key_var.get().strip())

            sample = self.df.head(30).to_csv(index=False)
            context = (
                "You are a data analyst. Use the dataset sample and metadata to answer clearly.\n\n"
                f"Rows: {len(self.df)}\n"
                f"Columns: {len(self.df.columns)}\n"
                f"Column names: {', '.join([str(c) for c in self.df.columns])}\n\n"
                "CSV sample (first 30 rows):\n"
                f"{sample}\n"
            )

            response = client.chat.completions.create(
                model=self.model_var.get().strip(),
                messages=[
                    {"role": "system", "content": "You are a helpful and precise data analyst."},
                    {"role": "user", "content": context + "\nUser request:\n" + user_prompt},
                ],
                temperature=0.2,
            )

            answer = response.choices[0].message.content or "No response returned by model."
            self.root.after(0, self._show_output, answer)
        except Exception as exc:
            self.root.after(0, self._show_output, f"OpenAI request failed:\n{exc}")

    def _show_output(self, text: str) -> None:
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text)
        self.run_btn.configure(state="normal")
        self.status_var.set("Done")

    def download_report(self) -> None:
        report_text = self.output_text.get("1.0", "end").strip()
        if not report_text:
            messagebox.showwarning("No Report", "Generate analysis first, then download the report.")
            return

        report_format = self.report_format_var.get().strip().upper() or "TXT"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = ".html" if report_format == "HTML" else ".txt"
        default_name = f"dataset_report_{timestamp}{extension}"

        save_path = filedialog.asksaveasfilename(
            title="Save Report",
            defaultextension=extension,
            initialfile=default_name,
            filetypes=[("HTML Files", "*.html"), ("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not save_path:
            return

        source_name = Path(self.file_var.get()).name if self.file_var.get() != "No CSV selected" else "N/A"
        rows = len(self.df) if self.df is not None else 0
        cols = len(self.df.columns) if self.df is not None else 0
        created_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            if report_format == "HTML":
                html_content = (
                    "<!doctype html>\n"
                    "<html><head><meta charset='utf-8'><title>CSV Analysis Report</title>"
                    "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#0f172a;}"
                    "h1{margin-bottom:4px;}"
                    ".meta{color:#475569;margin-bottom:16px;}"
                    "pre{background:#f8fafc;border:1px solid #e2e8f0;padding:14px;border-radius:8px;white-space:pre-wrap;}"
                    "</style></head><body>"
                    "<h1>CSV Analysis Report</h1>"
                    f"<div class='meta'>Created: {escape(created_on)}<br>"
                    f"Source CSV: {escape(source_name)}<br>"
                    f"Rows: {rows} | Columns: {cols}</div>"
                    f"<pre>{escape(report_text)}</pre>"
                    "</body></html>"
                )
                with open(save_path, "w", encoding="utf-8") as handle:
                    handle.write(html_content)
            else:
                txt_content = (
                    "CSV Analysis Report\n"
                    "=" * 70
                    + "\n"
                    + f"Created: {created_on}\n"
                    + f"Source CSV: {source_name}\n"
                    + f"Rows: {rows}\n"
                    + f"Columns: {cols}\n\n"
                    + report_text
                )
                with open(save_path, "w", encoding="utf-8") as handle:
                    handle.write(txt_content)

            self.status_var.set("Report downloaded")
            messagebox.showinfo("Success", f"Report saved successfully:\n{save_path}")
        except Exception as exc:
            messagebox.showerror("Save Error", f"Failed to save report:\n{exc}")


def main() -> None:
    root = tk.Tk()
    CsvOpenAIApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
