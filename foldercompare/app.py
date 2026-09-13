from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import CompareEntry, CompareState, EntryType, copy_selected, compare_trees, path_present, validate_root_pair


DISPLAY_STATE = {
    CompareState.SAME: "Verified",
    CompareState.MODIFIED: "Changed",
    CompareState.LEFT_ONLY: "Missing from copy",
    CompareState.RIGHT_ONLY: "Extra in copy",
}
FILTERS = ("Problems only", "Everything", "Verified", "Changed", "Missing from copy", "Extra in copy")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("FolderCompare")
        self.geometry("1080x720")
        self.minsize(860, 580)
        self.configure(bg="#f6f7f9")
        self.left_var = tk.StringVar()
        self.right_var = tk.StringVar()
        self.full_var = tk.BooleanVar(value=False)
        self.filter_var = tk.StringVar(value="Problems only")
        self.status_var = tk.StringVar(value="Choose the original folder and the copy you want to verify.")
        self.verdict_var = tk.StringVar(value="Comparison is read-only. Nothing changes until you explicitly copy an item.")
        self.count_vars = {s: tk.StringVar(value="0") for s in CompareState}
        self.entries: dict[str, CompareEntry] = {}
        self.path_to_iid: dict[str, str] = {}
        self.final_results: list[CompareEntry] = []
        self._comparison_roots: tuple[str, str] | None = None
        self._events: queue.Queue = queue.Queue()
        self._busy = False
        self._build_style()
        self._build_ui()
        self.left_var.trace_add("write", self._root_edited)
        self.right_var.trace_add("write", self._root_edited)
        self.full_var.trace_add("write", self._verification_mode_edited)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
        style.configure("Verdict.TLabel", font=("Segoe UI Semibold", 12), foreground="#111827")
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
        ttk.Label(header, text="Did the files copy? Verify their contents.", style="Verdict.TLabel").pack(anchor="w", pady=(3, 0))
        ttk.Label(header, text="Verify ordinary file data and tree presence in a copy, backup, migration, or restored drive — without sync or merge rules.", style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        pickers = ttk.Frame(outer)
        pickers.pack(fill="x")
        self.path_entries: list[ttk.Entry] = []
        self.browse_buttons: list[ttk.Button] = []
        for col, (label, var) in enumerate((("Original folder", self.left_var), ("Copy / backup folder", self.right_var))):
            box = ttk.Frame(pickers, style="Card.TFrame", padding=12)
            box.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0))
            ttk.Label(box, text=label, style="CardTitle.TLabel").pack(anchor="w")
            row = ttk.Frame(box, style="Card.TFrame")
            row.pack(fill="x", pady=(6, 0))
            ent = ttk.Entry(row, textvariable=var)
            ent.pack(side="left", fill="x", expand=True)
            btn = ttk.Button(row, text="Browse", command=lambda v=var: self._browse(v))
            btn.pack(side="left", padx=(8, 0))
            self.path_entries.append(ent)
            self.browse_buttons.append(btn)
        pickers.columnconfigure(0, weight=1)
        pickers.columnconfigure(1, weight=1)

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=12)
        self.compare_btn = ttk.Button(controls, text="Verify folders", style="Primary.TButton", command=self.compare)
        self.compare_btn.pack(side="left")
        self.full_check = ttk.Checkbutton(controls, text="Extra assurance: byte-for-byte verify matches", variable=self.full_var)
        self.full_check.pack(side="left", padx=14)
        self.copy_btn = ttk.Button(controls, text="Copy missing file → backup", command=self._copy, state="disabled", underline=0)
        self.copy_btn.pack(side="right")
        self.bind_all("<Alt-c>", lambda _event: self.copy_btn.invoke())

        ttk.Label(outer, textvariable=self.verdict_var, style="Verdict.TLabel").pack(fill="x", pady=(0, 10))

        cards = ttk.Frame(outer)
        cards.pack(fill="x", pady=(0, 10))
        for i, state in enumerate((CompareState.SAME, CompareState.MODIFIED, CompareState.LEFT_ONLY, CompareState.RIGHT_ONLY)):
            card = ttk.Frame(cards, style="Card.TFrame", padding=(14, 10))
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 0 if i == 3 else 5))
            ttk.Label(card, text=DISPLAY_STATE[state], style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=self.count_vars[state], style="CardValue.TLabel").pack(anchor="w")
            cards.columnconfigure(i, weight=1)

        filter_row = ttk.Frame(outer)
        filter_row.pack(fill="x", pady=(0, 8))
        ttk.Label(filter_row, text="Show:").pack(side="left")
        self.filter_box = ttk.Combobox(filter_row, textvariable=self.filter_var, values=FILTERS, state="readonly", width=18)
        self.filter_box.pack(side="left", padx=(7, 0))
        self.filter_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())
        ttk.Label(filter_row, text="Problems only keeps verified matches out of the way.", style="Sub.TLabel").pack(side="left", padx=10)

        table = ttk.Frame(outer, style="Card.TFrame")
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("state", "kind", "left", "right", "detail"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Path")
        self.tree.heading("state", text="Result")
        self.tree.heading("kind", text="Type")
        self.tree.heading("left", text="Original")
        self.tree.heading("right", text="Copy")
        self.tree.heading("detail", text="Why")
        self.tree.column("#0", width=330, minwidth=180)
        self.tree.column("state", width=125, anchor="center")
        self.tree.column("kind", width=75, anchor="center")
        self.tree.column("left", width=90, anchor="e")
        self.tree.column("right", width=90, anchor="e")
        self.tree.column("detail", width=250)
        self.tree.tag_configure("Same", foreground="#246b47")
        self.tree.tag_configure("Modified", foreground="#9a5a00")
        self.tree.tag_configure("Left only", foreground="#2457a6")
        self.tree.tag_configure("Right only", foreground="#7a3e9d")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_copy_state())
        ybar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ybar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        ttk.Label(outer, textvariable=self.status_var, style="Sub.TLabel").pack(fill="x", pady=(9, 0))

    def _browse(self, var: tk.StringVar) -> None:
        chosen = filedialog.askdirectory(mustexist=True)
        if chosen:
            var.set(chosen)

    def _root_edited(self, *_args) -> None:
        if self._comparison_roots is not None and not self._busy:
            self._comparison_roots = None
            self.final_results = []
            self._clear_tree()
            self.copy_btn.configure(state="disabled")
            self.verdict_var.set("Folders changed — verify again before copying anything.")

    def _verification_mode_edited(self, *_args) -> None:
        if self._busy:
            return
        if self._comparison_roots is not None:
            self._comparison_roots = None
            self.final_results = []
            self._clear_tree()
            self.copy_btn.configure(state="disabled")
            self.verdict_var.set("Verification mode changed — verify again.")

    def _on_close(self) -> None:
        if self._busy:
            messagebox.showinfo("FolderCompare is working", "Please wait for the current operation to finish.")
            return
        self.destroy()

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

    def _clear_tree(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        self.entries.clear()
        self.path_to_iid.clear()

    def _clear_all(self) -> None:
        self._clear_tree()
        self.final_results = []
        self._comparison_roots = None
        for var in self.count_vars.values():
            var.set("0")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.compare_btn.configure(state="disabled" if busy else "normal")
        for widget in self.path_entries + self.browse_buttons:
            widget.configure(state="disabled" if busy else "normal")
        self.filter_box.configure(state="disabled" if busy else "readonly")
        self.full_check.configure(state="disabled" if busy else "normal")
        self.copy_btn.configure(state="disabled")
        if not busy:
            self._update_copy_state()

    def compare(self) -> None:
        if self._busy:
            return
        left, right = self.left_var.get().strip(), self.right_var.get().strip()
        try:
            left_path, right_path = validate_root_pair(left, right)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Choose safe folders", str(exc))
            return
        self._clear_all()
        self._set_busy(True)
        self.status_var.set("Scanning both folders and verifying content…")
        self.verdict_var.set("Verification in progress. Comparison is read-only.")
        full = self.full_var.get()
        roots = (str(left_path), str(right_path))

        def worker() -> None:
            try:
                results = compare_trees(left_path, right_path, full_verify=full)
                self._events.put(("done", (results, roots)))
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
        iid = self.tree.insert(parent_parent, "end", text=Path(parent_path).name, values=("", "Folder", "—", "—", ""), open=True)
        self.path_to_iid[parent_path] = iid
        return iid

    def _upsert(self, entry: CompareEntry) -> None:
        left_size = entry.left.size if entry.left else None
        right_size = entry.right.size if entry.right else None
        values = (DISPLAY_STATE[entry.state], entry.kind.value, self._fmt_size(left_size), self._fmt_size(right_size), entry.detail)
        iid = self.path_to_iid.get(entry.rel_path)
        if iid:
            self.tree.item(iid, text=Path(entry.rel_path).name, values=values, tags=(entry.state.value,))
        else:
            parent = self._ensure_parent(entry.rel_path)
            iid = self.tree.insert(parent, "end", text=Path(entry.rel_path).name, values=values, tags=(entry.state.value,), open=True)
            self.path_to_iid[entry.rel_path] = iid
        self.entries[iid] = entry

    def _matches_filter(self, entry: CompareEntry) -> bool:
        choice = self.filter_var.get()
        if choice == "Everything":
            return True
        if choice == "Problems only":
            return entry.state is not CompareState.SAME
        return DISPLAY_STATE[entry.state] == choice

    def _apply_filter(self) -> None:
        self._clear_tree()
        first_repairable: str | None = None
        for entry in self.final_results:
            if self._matches_filter(entry):
                self._upsert(entry)
                if (first_repairable is None
                        and entry.state is CompareState.LEFT_ONLY
                        and entry.kind is EntryType.FILE
                        and entry.left is not None):
                    first_repairable = self.path_to_iid.get(entry.rel_path)
        if first_repairable:
            self.tree.selection_set(first_repairable)
            self.tree.focus(first_repairable)
            self.tree.see(first_repairable)
        self._update_copy_state()

    def _drain_events(self) -> None:
        handled = 0
        while handled < 50:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            handled += 1
            if kind == "done":
                results, roots = payload
                self.final_results = results
                self._comparison_roots = roots
                final_counts = {s: 0 for s in CompareState}
                for e in results:
                    final_counts[e.state] += 1
                for s, n in final_counts.items():
                    self.count_vars[s].set(str(n))
                problems = len(results) - final_counts[CompareState.SAME]
                if problems == 0:
                    self.verdict_var.set(f"Everything matches — {len(results)} items verified by content.")
                else:
                    self.verdict_var.set(f"{problems} items need attention — {final_counts[CompareState.SAME]} verified matches are hidden by default.")
                self.status_var.set("Verification complete. 'Verified' always includes a content check.")
                self._set_busy(False)
                self._apply_filter()
                return
            if kind == "error":
                self._set_busy(False)
                self.status_var.set("Verification failed. No files were changed.")
                self.verdict_var.set("Could not complete verification.")
                messagebox.showerror("Verification failed", str(payload))
                return
            if kind == "copy_done":
                destination = payload
                self._set_busy(False)
                self.status_var.set(f"Copy completed and verified: {destination}")
                self.after(50, self.compare)
                return
            if kind == "copy_error":
                self._set_busy(False)
                self.status_var.set("Copy failed safely. Existing destination data was not overwritten.")
                messagebox.showerror("Copy failed safely", str(payload))
                return
        if self._busy:
            self.after(40, self._drain_events)

    def _selected_entry(self) -> CompareEntry | None:
        selected = self.tree.selection()
        if not selected:
            return None
        return self.entries.get(selected[0])

    def _update_copy_state(self) -> None:
        entry = self._selected_entry()
        allowed = (
            not self._busy
            and self._comparison_roots is not None
            and entry is not None
            and entry.state is CompareState.LEFT_ONLY
            and entry.kind is EntryType.FILE
            and entry.left is not None
        )
        self.copy_btn.configure(state="normal" if allowed else "disabled")

    def _copy(self) -> None:
        if self._busy or self._comparison_roots is None:
            return
        entry = self._selected_entry()
        if entry is None or entry.state is not CompareState.LEFT_ONLY or entry.kind is not EntryType.FILE:
            messagebox.showinfo("Nothing safe to copy", "Choose a file that is missing from the copy. Changed files and folders are compare-only in this safety-first release.")
            return
        src_root, dst_root = self._comparison_roots
        src = Path(src_root) / entry.rel_path
        dst = Path(dst_root) / entry.rel_path
        if path_present(dst):
            self._comparison_roots = None
            self.copy_btn.configure(state="disabled")
            messagebox.showerror("Destination changed", "The destination now exists. Verify the folders again; FolderCompare will not overwrite it.")
            return
        prompt = f"Original → Copy / backup\n\nSource:\n{src}\n\nDestination:\n{dst}\n\nThis action adds the missing file only. Existing data is never overwritten.\n\nProceed?"
        if not messagebox.askyesno("Confirm copy to backup", prompt, icon="question", default="no"):
            return
        self._set_busy(True)
        self.status_var.set("Staging and verifying the missing file before safe publication…")

        def worker() -> None:
            try:
                copy_selected(src_root, dst_root, entry.rel_path, overwrite=False)
                self._events.put(("copy_done", dst))
            except Exception as exc:
                self._events.put(("copy_error", exc))
        threading.Thread(target=worker, daemon=True).start()
        self.after(40, self._drain_events)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Verify that a folder copy or backup matches its original.")
    parser.add_argument("--left", help="Preselect the original folder")
    parser.add_argument("--right", help="Preselect the copy / backup folder")
    parser.add_argument("--verify", action="store_true", help="Verify matching files byte-for-byte")
    args = parser.parse_args()
    app = App()
    if args.left:
        app.left_var.set(args.left)
    if args.right:
        app.right_var.set(args.right)
    if args.verify:
        app.full_var.set(True)
    if args.left and args.right:
        app.after(250, app.compare)
    app.mainloop()
