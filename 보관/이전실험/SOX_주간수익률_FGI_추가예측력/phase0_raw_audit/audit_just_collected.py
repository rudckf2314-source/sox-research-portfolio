"""Read-only inspection of files supplied in 방금수집/."""

import csv
import hashlib
from collections import deque
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "방금수집"

for path in sorted(SOURCE.iterdir()):
    print("\nFILE", ascii(path.name), "bytes", path.stat().st_size,
          "sha256", hashlib.sha256(path.read_bytes()).hexdigest())
    if path.suffix.lower() == ".xlsx":
        book = load_workbook(path, read_only=True, data_only=True)
        for sheet in book:
            print("SHEET", sheet.title, "rows", sheet.max_row, "cols", sheet.max_column)
            first, last = [], deque(maxlen=4)
            for index, row in enumerate(sheet.values):
                if index < 12:
                    first.append(row[:12])
                if any(value is not None for value in row):
                    last.append(row[:12])
            print("FIRST", ascii(first))
            print("LAST", ascii(list(last)))
        continue
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp950", "big5", "cp949"):
        try:
            content = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        encoding, content = "utf-8-replace", raw.decode("utf-8", errors="replace")
    lines = content.splitlines()
    print("ENCODING", encoding, "lines", len(lines))
    print("FIRST", ascii(lines[:5]))
    print("LAST", ascii(lines[-5:]))
    try:
        reader = csv.reader(lines)
        print("HEADERS", ascii(next(reader)), ascii(next(reader)))
    except Exception as exc:
        print("CSV_READ_ERROR", type(exc).__name__)
