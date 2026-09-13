from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import CompareEntry, CompareState, copy_selected, compare_trees


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("FolderCompare")
        self.geometry("1080x720")
        self.minsize(820, 560)
        self.configure(bg="#f6f7f9")
        self.left_var = tk.StringVar()
        self.right_var = tk.StringVar()
        self.full_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Choose two folders to begin.")
        self.count_vars = {s: tk.StringVar(value="0") for s in CompareState}
        self.entries: dict[str, CompareEntry] = {}
        self.path_to_iid: dict[str, str] = {}
        self._events: queue.Queue = queue.Queue()
        self._busy = False
        self._build_style()
        self._build_ui()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f6f7f9")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabel", background="#f6f7f9", foreground="#172033", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 21), foreground="#111827")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#667085")
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#667085", font=("Segoe UI", 9))
        style.configure("CardValue.TLabel", background="#ffffff", foreground="#111827", font=("Segoe UI Semibold", 17))
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10), padding=(16, 9))
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 8))
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=28, background="#ffffff", fieldbackground="#ffffff", borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), padding=(6, 8))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=20)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="FolderCompare", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Open two folders. See what differs.", style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        pickers = ttk.Frame(outer)
        pickers.pack(fill="x")
        for col, (label, var) in enumerate((("Left folder", self.left_var), ("Right folder", self.right_var))):
            box = ttk.Frame(pickers, style="Card.TFrame", padding=12)
            box.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0))
            ttk.Label(box, text=label, style="CardTitle.TLabel").pack(anchor="w")
            row = ttk.Frame(box, style="Card.TFrame")
            row.pack(fill="x", pady=(6, 0))
            ent = ttk.Entry(row, textvariable=var)
            ent.pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse", command=lambda v=var: self._browse(v)).pack(side="left", padx=(8, 0))
        pickers.columnconfigure(0, weight=1)
        pickers.columnconfigure(1, weight=1)

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=12)
        self.compare_btn = ttk.Button(controls, text="Compare folders", style="Primary.TButton", command=self.compare)
        self.compare_btn.pack(side="left")
        ttk.Checkbutton(controls, text="Verify contents fully (byte-for-byte)", variable=self.full_var).pack(side="left", padx=14)
        ttk.Button(controls, text="Copy →", command=lambda: self._copy("left")).pack(side="right", padx=(6, 0))
        ttk.Button(controls, text="← Copy", command=lambda: self._copy("right")).pack(side="right")

        cards = ttk.Frame(outer)
        cards.pack(fill="x", pady=(0, 12))
        labels = [CompareState.SAME, CompareState.MODIFIED, CompareState.LEFT_ONLY, CompareState.RIGHT_ONLY]
        for i, state in enumerate(labels):
            card = ttk.Frame(cards, style="Card.TFrame", padding=(14, 10))
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 0 if i == 3 else 5))
            ttk.Label(card, text=state.value, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=self.count_vars[state], style="CardValue.TLabel").pack(anchor="w")
            cards.columnconfigure(i, weight=1)

        table = ttk.Frame(outer, style="Card.TFrame")
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("state", "kind", "left", "right", "detail"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Path")
        self.tree.heading("state", text="State")
        self.tree.heading("kind", text="Type")
        self.tree.heading("left", text="Left size")
        self.tree.heading("right", text="Right size")
        self.tree.heading("detail", text="Why")
        self.tree.column("#0", width=330, minwidth=180)
        self.tree.column("state", width=95, anchor="center")
        self.tree.column("kind", width=75, anchor="center")
        self.tree.column("left", width=90, anchor="e")
        self.tree.column("right", width=90, anchor="e")
        self.tree.column("detail", width=230)
        self.tree.tag_configure("Same", foreground="#246b47")
        self.tree.tag_configure("Modified", foreground="#9a5a00")
        self.tree.tag_configure("Left only", foreground="#2457a6")
        self.tree.tag_configure("Right only", foreground="#7a3e9d")
        ybar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ybar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        ttk.Label(outer, textvariable=self.status_var, style="Sub.TLabel").pack(fill="x", pady=(9, 0))

    def _browse(self, var: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(mustexist=True)
        if chosen:
            var.set(chosen)

    @staticmethod
    def _fmt_size(value: int | None) -> str:
        if value is None:
            return "—"
        n = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024 or unit == "TB":
                return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return str(value)

    def _clear(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        self.entries.clear()
        self.path_to_iid.clear()
        for var in self.count_vars.values():
            var.set("0")

    def compare(self) -> None:
        if self._busy:
            return
        left, right = self.left_var.get().strip(), self.right_var.get().strip()
        if not Path(left).is_dir() or not Path(right).is_dir():
            messagebox.showerror("Choose folders", "Choose two existing folders first.")
            return
        self._clear()
        self._busy = True
        self.compare_btn.configure(state="disabled")
        self.status_var.set("Scanning and comparing…")
        full = self.full_var.get()

        def worker() -> None:
            try:
                def emit(entry: CompareEntry) -> None:
                    self._events.put(("entry", entry))
                results = compare_trees(left, right, full_verify=full, on_entry=emit)
                self._events.put(("done", results))
            except Exception as exc:
                self._events.put(("error", exc))
        threading.Thread(target=worker, daemon=True).start()
        self.after(40, self._drain_events)

    def _ensure_parent(self, rel: str) -> str:
        parent_path = str(Path(rel).parent).replace("\\", "/")
        if parent_path in (".", ""):
            return ""
        if parent_path in self.path_to_iid:
            return self.path_to_iid[parent_path]
        parent_parent = self._ensure_parent(parent_path)
        iid = self.tree.insert(parent_parent, "end", text=Path(parent_path).name, values=("…", "Folder", "—", "—", "comparing"), open=True)
        self.path_to_iid[parent_path] = iid
        return iid

    def _upsert(self, entry: CompareEntry) -> None:
        left_size = entry.left.size if entry.left else None
        right_size = entry.right.size if entry.right else None
        values = (entry.state.value, entry.kind.value, self._fmt_size(left_size), self._fmt_size(right_size), entry.detail)
        iid = self.path_to_iid.get(entry.rel_path)
        if iid:
            self.tree.item(iid, text=Path(entry.rel_path).name, values=values, tags=(entry.state.value,))
        else:
            parent = self._ensure_parent(entry.rel_path)
            iid = self.tree.insert(parent, "end", text=Path(entry.rel_path).name, values=values, tags=(entry.state.value,), open=True)
            self.path_to_iid[entry.rel_path] = iid
        self.entries[iid] = entry

    def _drain_events(self) -> None:
        counts = {s: int(self.count_vars[s].get()) for s in CompareState}
        handled = 0
        while handled < 200:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            handled += 1
            if kind == "entry":
                entry: CompareEntry = payload
                self._upsert(entry)
                counts[entry.state] += 1
                self.count_vars[entry.state].set(str(counts[entry.state]))
                self.status_var.set(f"Compared {sum(counts.values())} items…")
            elif kind == "done":
                # Recompute counts because folders may have appeared as placeholders before finalization.
                results: list[CompareEntry] = payload
                final_counts = {s: 0 for s in CompareState}
                for e in results:
                    final_counts[e.state] += 1
                for s, n in final_counts.items():
                    self.count_vars[s].set(str(n))
                self._busy = False
                self.compare_btn.configure(state="normal")
                self.status_var.set(f"Done — {len(results)} items compared. Same always includes a content check.")
                return
            elif kind == "error":
                self._busy = False
                self.compare_btn.configure(state="normal")
                self.status_var.set("Comparison failed.")
                messagebox.showerror("Comparison failed", str(payload))
                return
        if self._busy:
            self.after(40, self._drain_events)

    def _copy(self, direction: str) -> None:
        selected = self.tree.selection()
        if not selected or selected[0] not in self.entries:
            messagebox.showinfo("Select an item", "Select a compared file, folder, or link first.")
            return
        entry = self.entries[selected[0]]
        if direction == "left":
            src_root, dst_root = self.left_var.get(), self.right_var.get()
            label = "Left → Right"
        else:
            src_root, dst_root = self.right_var.get(), self.left_var.get()
            label = "Right → Left"
        src = Path(src_root) / entry.rel_path
        dst = Path(dst_root) / entry.rel_path
        if not src.exists() and not src.is_symlink():
            messagebox.showerror("Source missing", f"Source does not exist:\n\n{src}")
            return
        overwrite = dst.exists() or dst.is_symlink()
        prompt = f"{label}\n\nSource:\n{src}\n\nDestination:\n{dst}\n\nOverwrite: {'YES' if overwrite else 'NO'}\n\nProceed?"
        if not messagebox.askyesno("Confirm exact copy", prompt, icon="warning" if overwrite else "question"):
            return
        try:
            copy_selected(src_root, dst_root, entry.rel_path, overwrite=overwrite)
        except Exception as exc:
            messagebox.showerror("Copy failed", str(exc))
            return
        self.status_var.set(f"Copied exactly to {dst}")
        self.after(100, self.compare)


def main() -> None:
    App().mainloop()
