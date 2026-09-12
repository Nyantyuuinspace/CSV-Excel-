"""CSV Workbench の処理本体。GUI に依存しないため単体でも利用できる。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import os
import tempfile


class ProcessingError(Exception):
    """入力や設定に原因があるエラー。"""


@dataclass(frozen=True)
class Options:
    remove_duplicates: bool = True
    blank_mode: str = "keep"  # keep, fill, drop
    fill_value: str = ""
    sort_column: str = ""
    sort_numeric: bool = False
    descending: bool = False
    sum_column: str = ""
    group_column: str = ""


@dataclass(frozen=True)
class Result:
    input_files: int
    input_rows: int
    output_rows: int
    removed_rows: int
    output_path: Path
    summary_path: Path | None


def list_csv_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise ProcessingError(f"入力フォルダが見つかりません: {folder}")
    files = sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".csv"),
        key=lambda p: p.name.casefold(),
    )
    if not files:
        raise ProcessingError(f"入力フォルダにCSVがありません: {folder}")
    return files


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    last_decode_error = None
    for encoding in ("utf-8-sig", "cp932"):
        try:
            with path.open("r", encoding=encoding, newline="") as source:
                reader = csv.reader(source, strict=True)
                header = next(reader, None)
                if not header or not any(header):
                    raise ProcessingError(f"見出し行がありません: {path.name}")
                if any(not name.strip() for name in header) or len(set(header)) != len(header):
                    raise ProcessingError(f"見出しに空欄か重複があります: {path.name}")
                rows = []
                for line_number, cells in enumerate(reader, start=2):
                    if len(cells) != len(header):
                        raise ProcessingError(
                            f"{path.name} の{line_number}行目: 列数が見出しと異なります"
                            f"（見出し{len(header)}列、データ{len(cells)}列）"
                        )
                    rows.append(dict(zip(header, cells)))
                return header, rows
        except UnicodeDecodeError as exc:
            last_decode_error = exc
        except (OSError, csv.Error) as exc:
            raise ProcessingError(f"{path.name} を読み込めません: {exc}") from exc
    raise ProcessingError(f"{path.name}: UTF-8/CP932で読めません。CSVの文字コードを確認してください") from last_decode_error


def read_headers(files: list[Path]) -> list[str]:
    if not files:
        raise ProcessingError("CSVを選択してください")
    header, _ = _read_csv(files[0])
    return header


def _decimal(value: str, context: str) -> Decimal:
    try:
        number = Decimal(value.strip())
    except InvalidOperation as exc:
        raise ProcessingError(f"{context}: 数値ではありません: {value!r}") from exc
    if not number.is_finite():
        raise ProcessingError(f"{context}: 無限大やNaNは使用できません")
    return number


def _safe_cell(value: str) -> str:
    # 表計算ソフトが数式と解釈するセルは文字列として出力する。
    trimmed = value.lstrip(" \t\r\n")
    if trimmed.startswith(("=", "+", "@", "\t", "\r")):
        return "'" + value
    if trimmed.startswith("-"):
        try:
            _decimal(trimmed, "出力")
            return value
        except ProcessingError:
            return "'" + value
    if value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=path.parent,
            prefix=".csv-workbench-", suffix=".tmp", delete=False,
        ) as target:
            temporary = Path(target.name)
            writer = csv.writer(target)
            writer.writerow([_safe_cell(value) for value in header])
            writer.writerows([_safe_cell(value) for value in row] for row in rows)
        # 同名ファイルが直前に作られても上書きしない。WindowsのNTFSを含む同一ファイルシステムで動く。
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def process(files: list[Path], output: Path, options: Options) -> Result:
    if not files:
        raise ProcessingError("CSVを選択してください")
    if options.blank_mode not in {"keep", "fill", "drop"}:
        raise ProcessingError("空欄処理の指定が無効です")
    if options.group_column and not options.sum_column:
        raise ProcessingError("グループ集計には合計する数値列を選んでください")
    files = sorted((Path(p) for p in files), key=lambda p: str(p).casefold())
    output = Path(output)
    if output.suffix.lower() != ".csv" or not output.parent.is_dir():
        raise ProcessingError("出力先は既存フォルダ内の .csv ファイルにしてください")
    summary = output.with_name(output.stem + "_summary.csv") if options.sum_column else None
    input_paths = {p.resolve() for p in files}
    if output.resolve() in input_paths or (summary and summary.resolve() in input_paths):
        raise ProcessingError("入力CSVを出力先に指定できません")
    for destination in (output, summary):
        if destination and destination.exists():
            raise ProcessingError(f"出力先に同名ファイルがあります。別名を指定してください: {destination.name}")

    headers = None
    combined = []
    for path in files:
        if not path.is_file() or path.suffix.lower() != ".csv":
            raise ProcessingError(f"CSVファイルが見つかりません: {path}")
        current, rows = _read_csv(path)
        if headers is None:
            headers = current
            for selected in (options.sort_column, options.sum_column, options.group_column):
                if selected and selected not in headers:
                    raise ProcessingError(f"指定した列がありません: {selected}")
        elif current != headers:
            raise ProcessingError(f"{path.name}: 見出しの名前または順番が最初のCSVと異なります")
        combined.extend(rows)

    assert headers is not None
    input_rows = len(combined)
    if options.blank_mode == "drop":
        combined = [row for row in combined if all(value.strip() for value in row.values())]
    elif options.blank_mode == "fill":
        combined = [
            {name: (value if value.strip() else options.fill_value) for name, value in row.items()}
            for row in combined
        ]
    if options.remove_duplicates:
        seen = set()
        unique = []
        for row in combined:
            key = tuple(row[name] for name in headers)
            if key not in seen:
                seen.add(key)
                unique.append(row)
        combined = unique

    if options.sort_column:
        column = options.sort_column
        if options.sort_numeric:
            for index, row in enumerate(combined, 1):
                if row[column].strip():
                    _decimal(row[column], f"並び替え列「{column}」の処理後{index}行目")
            sort_key = lambda row: _decimal(row[column], "並び替え") if row[column].strip() else Decimal(0)
        else:
            sort_key = lambda row: row[column].casefold()
        nonblank = [row for row in combined if row[column].strip()]
        blank = [row for row in combined if not row[column].strip()]
        combined = sorted(nonblank, key=sort_key, reverse=options.descending) + blank

    summary_rows = []
    if options.sum_column:
        totals: dict[str, Decimal] = {}
        for index, row in enumerate(combined, 1):
            key = row[options.group_column] if options.group_column else ""
            totals.setdefault(key, Decimal(0))
            if row[options.sum_column].strip():
                totals[key] += _decimal(row[options.sum_column], f"合計列「{options.sum_column}」の処理後{index}行目")
        if not options.group_column and not totals:
            totals[""] = Decimal(0)
        summary_rows = [[key, str(value)] for key, value in sorted(totals.items())] if options.group_column else [[str(totals[""])]]

    try:
        _write_csv(output, headers, [[row[name] for name in headers] for row in combined])
        if summary:
            title = f"{options.sum_column}_合計"
            _write_csv(summary, [options.group_column, title] if options.group_column else [title], summary_rows)
    except OSError as exc:
        raise ProcessingError(f"出力先に保存できません（権限や空き容量を確認）: {exc}") from exc
    return Result(len(files), input_rows, len(combined), input_rows - len(combined), output, summary)
