import csv
import tempfile
import unittest
from pathlib import Path

from processor import Options, ProcessingError, list_csv_files, process


def write_rows(path, rows, encoding="utf-8-sig"):
    with path.open("w", newline="", encoding=encoding) as file:
        csv.writer(file).writerows(rows)


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.reader(file))


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_mixed_encodings_dedup_fill_sort_and_group_sum(self):
        first = self.folder / "a.csv"
        second = self.folder / "b.csv"
        write_rows(first, [["区分", "名前", "金額"], ["東京", "りんご", "100"],
                           ["東京", "りんご", "100"], ["大阪", "", "20"]])
        write_rows(second, [["区分", "名前", "金額"], ["大阪", "みかん", "30"]], "cp932")
        output = self.folder / "result.csv"
        result = process(list_csv_files(self.folder), output,
                         Options(blank_mode="fill", fill_value="未設定", sort_column="金額",
                                 sort_numeric=True, descending=True, sum_column="金額", group_column="区分"))
        self.assertEqual((result.input_rows, result.output_rows, result.removed_rows), (4, 3, 1))
        self.assertEqual(read_rows(output)[1:], [["東京", "りんご", "100"],
                                                ["大阪", "みかん", "30"], ["大阪", "未設定", "20"]])
        self.assertEqual(read_rows(result.summary_path), [["区分", "金額_合計"],
                                                        ["大阪", "50"], ["東京", "100"]])
        with output.open("rb") as file:
            self.assertEqual(file.read(3), b"\xef\xbb\xbf")

    def test_drop_blanks_and_total(self):
        source = self.folder / "data.csv"
        write_rows(source, [["name", "amount"], ["A", "1.25"], ["B", ""], ["C", "2.75"]])
        result = process([source], self.folder / "out.csv", Options(blank_mode="drop", sum_column="amount"))
        self.assertEqual(result.output_rows, 2)
        self.assertEqual(read_rows(result.summary_path), [["amount_合計"], ["4.00"]])

    def test_mismatched_header_and_bad_number_do_not_write_output(self):
        a, b, output = (self.folder / name for name in ("a.csv", "b.csv", "out.csv"))
        write_rows(a, [["name", "amount"], ["A", "2"]])
        write_rows(b, [["amount", "name"], ["3", "B"]])
        with self.assertRaisesRegex(ProcessingError, "見出し"):
            process([a, b], output, Options())
        self.assertFalse(output.exists())
        write_rows(b, [["name", "amount"], ["B", "invalid"]])
        with self.assertRaisesRegex(ProcessingError, "数値ではありません"):
            process([a, b], output, Options(sum_column="amount"))
        self.assertFalse(output.exists())

    def test_input_and_existing_output_are_protected(self):
        a = self.folder / "a.csv"
        write_rows(a, [["v"], ["x"]])
        with self.assertRaisesRegex(ProcessingError, "入力CSV"):
            process([a], a, Options())
        output = self.folder / "out.csv"
        write_rows(output, [["old"]])
        with self.assertRaisesRegex(ProcessingError, "同名ファイル"):
            process([a], output, Options())
        self.assertEqual(read_rows(output), [["old"]])

    def test_spreadsheet_formula_cells_are_escaped(self):
        source, output = self.folder / "input.csv", self.folder / "safe.csv"
        write_rows(source, [["value"], ["=HYPERLINK(\"bad\")"], ["-2"], ["-2+cmd"], ["\t@x"]])
        process([source], output, Options(remove_duplicates=False))
        self.assertEqual(read_rows(output)[1:], [["'=HYPERLINK(\"bad\")"], ["-2"],
                                                ["'-2+cmd"], ["'\t@x"]])

    def test_invalid_row_width_reports_filename(self):
        source = self.folder / "bad.csv"
        write_rows(source, [["a", "b"], ["one"]])
        with self.assertRaisesRegex(ProcessingError, "bad.csv.*2行目"):
            process([source], self.folder / "out.csv", Options())


if __name__ == "__main__":
    unittest.main()
