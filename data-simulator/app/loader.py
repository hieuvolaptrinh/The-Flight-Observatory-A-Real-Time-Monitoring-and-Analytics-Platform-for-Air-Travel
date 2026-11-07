"""
Đọc toàn bộ CSV vào bộ nhớ một lần khi khởi động.
Trả về list các dict đã chuẩn hóa.
"""
import csv
from pathlib import Path
from typing import Any

REQUIRED_COLS = {
    "DAY_OF_WEEK", "FL_DATE", "OP_UNIQUE_CARRIER", "TAIL_NUM",
    "OP_CARRIER_FL_NUM", "ORIGIN_AIRPORT_ID", "ORIGIN_AIRPORT_SEQ_ID",
    "ORIGIN_CITY_MARKET_ID", "ORIGIN", "DEST_AIRPORT_ID",
    "DEST_AIRPORT_SEQ_ID", "DEST_CITY_MARKET_ID", "DEST",
    "CRS_DEP_TIME", "CRS_ARR_TIME", "CRS_ELAPSED_TIME", "DISTANCE",
}


def _parse_fl_date(raw: str) -> str:
    """'1/6/2025 12:00:00 AM'  →  '2025-01-06'"""
    from datetime import datetime
    raw = raw.strip()
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Cannot parse FL_DATE: '{raw}'")


def _pad_time(raw: str) -> str | None:
    """'829' → '0829', '' → None"""
    raw = raw.strip().split(".")[0]  # strip trailing .0
    if not raw:
        return None
    return f"{int(raw):04d}"


def _as_int(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    return int(float(raw))


def _as_float(raw: str) -> float | None:
    raw = raw.strip()
    return float(raw) if raw else None


def _as_str(raw: str) -> str | None:
    raw = raw.strip()
    return raw if raw else None


def load_records(csv_path: str) -> list[dict[str, Any]]:
    p = Path(csv_path)
    files = sorted(p.glob("*.csv")) if p.is_dir() else [p]
    if not files:
        raise FileNotFoundError(f"Không tìm thấy file CSV tại: {csv_path}")

    all_records: list[dict[str, Any]] = []

    for file in files:
        with open(file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            cols = set(reader.fieldnames or [])
            missing = REQUIRED_COLS - cols
            if missing:
                raise ValueError(f"{file.name} thiếu cột: {missing}")

            for row in reader:
                all_records.append({
                    "DAY_OF_WEEK":          _as_int(row["DAY_OF_WEEK"]),
                    "FL_DATE":              _parse_fl_date(row["FL_DATE"]),
                    "OP_UNIQUE_CARRIER":    _as_str(row["OP_UNIQUE_CARRIER"]),
                    "TAIL_NUM":             _as_str(row["TAIL_NUM"]),
                    "OP_CARRIER_FL_NUM":    _as_str(row["OP_CARRIER_FL_NUM"]),
                    "ORIGIN_AIRPORT_ID":    _as_int(row["ORIGIN_AIRPORT_ID"]),
                    "ORIGIN_AIRPORT_SEQ_ID":_as_int(row["ORIGIN_AIRPORT_SEQ_ID"]),
                    "ORIGIN_CITY_MARKET_ID":_as_int(row["ORIGIN_CITY_MARKET_ID"]),
                    "ORIGIN":               _as_str(row["ORIGIN"]),
                    "DEST_AIRPORT_ID":      _as_int(row["DEST_AIRPORT_ID"]),
                    "DEST_AIRPORT_SEQ_ID":  _as_int(row["DEST_AIRPORT_SEQ_ID"]),
                    "DEST_CITY_MARKET_ID":  _as_int(row["DEST_CITY_MARKET_ID"]),
                    "DEST":                 _as_str(row["DEST"]),
                    "CRS_DEP_TIME":         _pad_time(row["CRS_DEP_TIME"]),
                    "CRS_ARR_TIME":         _pad_time(row["CRS_ARR_TIME"]),
                    "CRS_ELAPSED_TIME":     _as_float(row["CRS_ELAPSED_TIME"]),
                    "DISTANCE":             _as_float(row["DISTANCE"]),
                })

    return all_records

