"""ダブルクリックでも起動できるCSV Workbench の画面。"""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from processor import Options, ProcessingError, list_csv_files, process, read_headers


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV Workbench — 一括結合・整理・集計")
        self.geometry("760x680")
        self.minsize(640, 590)
        self.files = []
        self.events = queue.Queue()
        self.output = tk.StringVar()
        self.blank = tk.StringVar(value="keep")
        self.fill = tk.StringVar()
        self.dedup = tk.BooleanVar(value=True)
        self.sort = tk.StringVar()
        self.numeric = tk.BooleanVar()
        self.descending = tk.BooleanVar()
        self.sum_col = tk.StringVar()
        self.group = tk.StringVar()
        self.status = tk.StringVar(value="CSVファイルまたはフォルダを選択してください")
        self._build()
        self.after(100, self._poll)

    def _build(self):
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="CSV Workbench", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="結合CSV：同じフォルダならファイル名順に読み込み、各CSV内の行順を保ちます。重複は先の行を残し、並び替え列を選んだ場合だけ行順を変更します。",
                  wraplength=690).pack(anchor="w", pady=(2, 2))
        ttk.Label(frame, text="集計CSV：合計列・グループ列は別ファイルの集計にだけ使います。入力CSVは変更しません。",
                  wraplength=690).pack(anchor="w", pady=(0, 10))

        source = ttk.LabelFrame(frame, text="1. 入力CSV", padding=10)
        source.pack(fill="both")
        buttons = ttk.Frame(source)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="フォルダを選択", command=self._choose_folder).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="ファイルを選択", command=self._choose_files).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="選択をクリア", command=self._clear).pack(side="left")
        self.file_list = tk.Listbox(source, height=5, exportselection=False)
        self.file_list.pack(fill="both", pady=(8, 0))

        actions = ttk.LabelFrame(frame, text="2. 処理内容", padding=10)
        actions.pack(fill="x", pady=12)
        ttk.Checkbutton(actions, text="重複する行を削除（全列が同じ行）", variable=self.dedup).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(actions, text="空欄の処理").grid(row=1, column=0, sticky="w", pady=(9, 0))
        ttk.Combobox(actions, textvariable=self.blank, state="readonly", width=15,
                     values=("keep", "fill", "drop")).grid(row=1, column=1, sticky="w", pady=(9, 0))
        ttk.Label(actions, text="keep: 維持 / fill: 補完 / drop: 行を除外").grid(row=1, column=2, sticky="w", padx=8, pady=(9, 0))
        ttk.Label(actions, text="補完する文字").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(actions, textvariable=self.fill, width=17).grid(row=2, column=1, sticky="w")
        ttk.Label(actions, text="並び替える列").grid(row=3, column=0, sticky="w")
        self.sort_box = ttk.Combobox(actions, textvariable=self.sort, state="readonly", width=17)
        self.sort_box.grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(actions, text="数値順", variable=self.numeric).grid(row=3, column=2, sticky="w")
        ttk.Checkbutton(actions, text="降順", variable=self.descending).grid(row=4, column=2, sticky="w")
        ttk.Label(actions, text="合計する数値列").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.sum_box = ttk.Combobox(actions, textvariable=self.sum_col, state="readonly", width=17)
        self.sum_box.grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Label(actions, text="グループ別集計列").grid(row=6, column=0, sticky="w", pady=6)
        self.group_box = ttk.Combobox(actions, textvariable=self.group, state="readonly", width=17)
        self.group_box.grid(row=6, column=1, sticky="w")
        ttk.Label(actions, text="列を空欄にすると処理を省略します").grid(
            row=7, column=0, columnspan=3, sticky="w")

        dest = ttk.LabelFrame(frame, text="3. 出力先（既存のファイルは上書きしません）", padding=10)
        dest.pack(fill="x")
        ttk.Entry(dest, textvariable=self.output).pack(side="left", fill="x", expand=True)
        ttk.Button(dest, text="保存先を選択", command=self._choose_output).pack(side="left", padx=(8, 0))
        self.run_button = ttk.Button(frame, text="処理を実行", command=self._run)
        self.run_button.pack(anchor="e", pady=(12, 6))
        ttk.Label(frame, textvariable=self.status, wraplength=690).pack(anchor="w")

    def _set_files(self, files):
        if not files:
            return
        try:
            headers = read_headers(files)
        except ProcessingError as exc:
            messagebox.showerror("CSVの読み込みエラー", str(exc))
            return
        self.files = files
        self.file_list.delete(0, "end")
        for path in files:
            self.file_list.insert("end", str(path))
        for box in (self.sort_box, self.sum_box, self.group_box):
            box["values"] = ("", *headers)
        for var in (self.sort, self.sum_col, self.group):
            var.set("")
        self.status.set(f"{len(files)}件のCSVを選択しました")

    def _choose_folder(self):
        folder = filedialog.askdirectory(title="CSVのあるフォルダを選択")
        if folder:
            try:
                self._set_files(list_csv_files(Path(folder)))
            except ProcessingError as exc:
                messagebox.showerror("入力エラー", str(exc))

    def _choose_files(self):
        paths = filedialog.askopenfilenames(title="CSVを選択", filetypes=[("CSV", "*.csv")])
        if paths:
            self._set_files([Path(path) for path in paths])

    def _clear(self):
        self.files = []
        self.file_list.delete(0, "end")
        for box in (self.sort_box, self.sum_box, self.group_box):
            box["values"] = ("",)
        for var in (self.sort, self.sum_col, self.group):
            var.set("")
        self.status.set("CSVファイルまたはフォルダを選択してください")

    def _choose_output(self):
        name = filedialog.asksaveasfilename(title="結合CSVの保存先", defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if name:
            self.output.set(name)

    def _run(self):
        if not self.files or not self.output.get().strip():
            messagebox.showerror("設定を確認", "入力CSVと出力先を選択してください")
            return
        options = Options(self.dedup.get(), self.blank.get(), self.fill.get(), self.sort.get(),
                          self.numeric.get(), self.descending.get(), self.sum_col.get(), self.group.get())
        self.run_button.configure(state="disabled")
        self.status.set("処理中です…")
        threading.Thread(target=self._worker, args=(list(self.files), Path(self.output.get()), options),
                         daemon=True).start()

    def _worker(self, files, output, options):
        try:
            self.events.put((True, process(files, output, options)))
        except (ProcessingError, OSError) as exc:
            self.events.put((False, str(exc)))
        except Exception as exc:
            self.events.put((False, f"予期しないエラー: {type(exc).__name__}: {exc}"))

    def _poll(self):
        try:
            ok, data = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.run_button.configure(state="normal")
            if ok:
                message = (f"{data.input_files}ファイル、{data.input_rows}行を読み込み、"
                           f"{data.output_rows}行を保存しました（除外{data.removed_rows}行）。\n"
                           f"結合CSV: {data.output_path}")
                if data.summary_path:
                    message += f"\n集計CSV: {data.summary_path}"
                self.status.set("処理が完了しました")
                messagebox.showinfo("完了", message)
            else:
                self.status.set("処理に失敗しました。原因を確認してください")
                messagebox.showerror("処理エラー", data)
        self.after(100, self._poll)


if __name__ == "__main__":
    App().mainloop()
