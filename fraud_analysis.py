import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

EXCEL_EPOCH = datetime(1899, 12, 30)
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELS_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


@dataclass
class BenfordResult:
    counts: dict
    total: int
    expected: dict
    actual_pct: dict


def excel_date_to_date(value: str):
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return None
    return EXCEL_EPOCH + timedelta(days=serial)


def to_float(value: str):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_xlsx(path: Path):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in sst.findall("a:si", NS):
                texts = [t.text or "" for t in si.findall(".//a:t", NS)]
                shared.append("".join(texts))

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheet = wb.find("a:sheets/a:sheet", NS)
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = None
        for rel in rels.findall("r:Relationship", RELS_NS):
            if rel.attrib["Id"] == rid:
                target = rel.attrib["Target"]
                break
        sheet_xml = ET.fromstring(z.read(f"xl/{target}"))

        rows = []
        for row in sheet_xml.findall("a:sheetData/a:row", NS):
            row_vals = {}
            for c in row.findall("a:c", NS):
                cell_ref = c.attrib["r"]
                col = "".join([ch for ch in cell_ref if ch.isalpha()])
                cell_type = c.attrib.get("t")
                v = c.find("a:v", NS)
                if v is None:
                    continue
                val = v.text
                if cell_type == "s":
                    val = shared[int(val)]
                row_vals[col] = val
            rows.append(row_vals)

    headers = rows[0]
    col_to_header = {col: header for col, header in headers.items()}
    records = []
    for row in rows[1:]:
        record = {}
        for col, val in row.items():
            header = col_to_header.get(col)
            if header is None:
                continue
            record[header] = val
        records.append(record)
    return records


def leading_digit(amount: float):
    if amount is None:
        return None
    value = abs(amount)
    if value < 1:
        return None
    while value >= 10:
        value /= 10
    return int(value)


def benford_analysis(amounts):
    counts = Counter()
    for amt in amounts:
        digit = leading_digit(amt)
        if digit is None:
            continue
        counts[digit] += 1
    total = sum(counts.values())
    expected = {d: (1 / d) for d in range(1, 10)}
    expected = {d: (expected[d] / sum(expected.values())) for d in expected}
    actual_pct = {d: (counts.get(d, 0) / total) if total else 0 for d in range(1, 10)}
    return BenfordResult(counts=counts, total=total, expected=expected, actual_pct=actual_pct)


def write_grouped_bar_svg(path: Path, title: str, labels, series, colors, width=900, height=420):
    margin_left = 80
    margin_bottom = 60
    margin_top = 50
    margin_right = 30
    chart_width = width - margin_left - margin_right
    chart_height = height - margin_top - margin_bottom
    max_value = max(max(values) for values in series.values()) if series else 1
    label_count = len(labels)
    group_width = chart_width / max(label_count, 1)
    bar_width = group_width / max(len(series), 1) * 0.7
    bar_spacing = (group_width - (bar_width * len(series))) / 2

    def y_for(value):
        return margin_top + chart_height - (value / max_value) * chart_height

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="28" text-anchor="middle" font-size="18" font-family="Arial">{title}</text>',
    ]

    # axes
    svg_lines.append(
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + chart_height}" stroke="#333"/>'
    )
    svg_lines.append(
        f'<line x1="{margin_left}" y1="{margin_top + chart_height}" x2="{margin_left + chart_width}" y2="{margin_top + chart_height}" stroke="#333"/>'
    )

    # gridlines and y-axis labels
    for i in range(6):
        value = max_value * i / 5
        y = y_for(value)
        svg_lines.append(
            f'<line x1="{margin_left}" y1="{y}" x2="{margin_left + chart_width}" y2="{y}" stroke="#e0e0e0"/>'
        )
        svg_lines.append(
            f'<text x="{margin_left - 10}" y="{y + 4}" text-anchor="end" font-size="11" font-family="Arial">{value:0.1f}</text>'
        )

    # bars
    for idx, label in enumerate(labels):
        group_x = margin_left + idx * group_width
        for s_idx, (series_name, values) in enumerate(series.items()):
            value = values[idx]
            bar_x = group_x + bar_spacing + s_idx * bar_width
            bar_y = y_for(value)
            bar_height = margin_top + chart_height - bar_y
            color = colors[s_idx % len(colors)]
            svg_lines.append(
                f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" fill="{color}"/>'
            )
        svg_lines.append(
            f'<text x="{group_x + group_width/2}" y="{margin_top + chart_height + 20}" text-anchor="middle" font-size="12" font-family="Arial">{label}</text>'
        )

    # legend
    legend_x = margin_left
    legend_y = margin_top - 10
    for s_idx, series_name in enumerate(series.keys()):
        color = colors[s_idx % len(colors)]
        svg_lines.append(
            f'<rect x="{legend_x}" y="{legend_y}" width="12" height="12" fill="{color}"/>'
        )
        svg_lines.append(
            f'<text x="{legend_x + 18}" y="{legend_y + 11}" font-size="12" font-family="Arial">{series_name}</text>'
        )
        legend_x += 150

    svg_lines.append("</svg>")
    path.write_text("\n".join(svg_lines), encoding="utf-8")


def write_bar_svg(path: Path, title: str, labels, values, color="#4c78a8", width=900, height=420):
    margin_left = 80
    margin_bottom = 60
    margin_top = 50
    margin_right = 30
    chart_width = width - margin_left - margin_right
    chart_height = height - margin_top - margin_bottom
    max_value = max(values) if values else 1
    bar_width = chart_width / max(len(labels), 1) * 0.7
    bar_spacing = (chart_width - bar_width * len(labels)) / max(len(labels), 1)

    def y_for(value):
        return margin_top + chart_height - (value / max_value) * chart_height

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="28" text-anchor="middle" font-size="18" font-family="Arial">{title}</text>',
    ]

    svg_lines.append(
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + chart_height}" stroke="#333"/>'
    )
    svg_lines.append(
        f'<line x1="{margin_left}" y1="{margin_top + chart_height}" x2="{margin_left + chart_width}" y2="{margin_top + chart_height}" stroke="#333"/>'
    )

    for i in range(6):
        value = max_value * i / 5
        y = y_for(value)
        svg_lines.append(
            f'<line x1="{margin_left}" y1="{y}" x2="{margin_left + chart_width}" y2="{y}" stroke="#e0e0e0"/>'
        )
        svg_lines.append(
            f'<text x="{margin_left - 10}" y="{y + 4}" text-anchor="end" font-size="11" font-family="Arial">{value:0.1f}</text>'
        )

    for idx, label in enumerate(labels):
        bar_x = margin_left + idx * (bar_width + bar_spacing) + bar_spacing / 2
        bar_y = y_for(values[idx])
        bar_height = margin_top + chart_height - bar_y
        svg_lines.append(
            f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" fill="{color}"/>'
        )
        svg_lines.append(
            f'<text x="{bar_x + bar_width/2}" y="{margin_top + chart_height + 20}" text-anchor="middle" font-size="11" font-family="Arial">{label}</text>'
        )

    svg_lines.append("</svg>")
    path.write_text("\n".join(svg_lines), encoding="utf-8")


def is_rounded(amount: float):
    if amount is None:
        return False
    cents = round(abs(amount) * 100)
    return cents % 100 == 0


def is_half_rounded(amount: float):
    if amount is None:
        return False
    cents = round(abs(amount) * 100)
    return cents % 50 == 0


def percentile(values, pct):
    if not values:
        return None
    values_sorted = sorted(values)
    k = int(round((len(values_sorted) - 1) * pct))
    return values_sorted[k]


def build_report(path: Path, output_path: Path):
    records = load_xlsx(path)

    for record in records:
        record["Debit"] = to_float(record.get("Debit"))
        record["Credit"] = to_float(record.get("Credit"))
        record["Amount"] = to_float(record.get("Amount"))
        abs_amount = to_float(record.get("AbsoluteAmount"))
        if abs_amount is None and record.get("Amount") is not None:
            abs_amount = abs(record["Amount"])
        record["AbsoluteAmount"] = abs_amount
        record["EffectiveDate"] = excel_date_to_date(record.get("EffectiveDate"))
        record["EntryDate"] = excel_date_to_date(record.get("EntryDate"))

    amounts = [r["AbsoluteAmount"] for r in records if r.get("AbsoluteAmount") is not None]
    p95 = percentile(amounts, 0.95)
    p99 = percentile(amounts, 0.99)

    benford = benford_analysis(amounts)

    preparer_stats = defaultdict(lambda: {
        "total": 0,
        "rounded": 0,
        "half_rounded": 0,
        "large_rounded": 0,
        "weekend": 0,
        "dup_key": 0,
        "amounts": [],
        "accounts": Counter(),
        "suspicious_lines": [],
    })

    dup_counter = Counter()
    for record in records:
        key = (
            record.get("PreparerID"),
            record.get("GLAccountNumber"),
            record.get("Amount"),
            record.get("EntryDate").date() if record.get("EntryDate") else None,
        )
        dup_counter[key] += 1

    for record in records:
        preparer = record.get("PreparerID")
        if not preparer:
            continue
        stats = preparer_stats[preparer]
        stats["total"] += 1
        amount = record.get("AbsoluteAmount")
        stats["amounts"].append(amount or 0)
        stats["accounts"][record.get("GLAccountNumber")] += 1

        rounded = is_rounded(amount)
        half_rounded = is_half_rounded(amount)
        if rounded:
            stats["rounded"] += 1
        if half_rounded:
            stats["half_rounded"] += 1
        if rounded and p95 is not None and amount is not None and amount >= p95:
            stats["large_rounded"] += 1

        entry_date = record.get("EntryDate")
        if entry_date and entry_date.weekday() >= 5:
            stats["weekend"] += 1

        key = (
            record.get("PreparerID"),
            record.get("GLAccountNumber"),
            record.get("Amount"),
            record.get("EntryDate").date() if record.get("EntryDate") else None,
        )
        if dup_counter[key] > 1:
            stats["dup_key"] += 1

        score = 0
        score += 2 if rounded and amount is not None and amount >= (p99 or 0) else 0
        score += 1 if rounded else 0
        score += 1 if entry_date and entry_date.weekday() >= 5 else 0
        score += 1 if dup_counter[key] > 1 else 0
        if score >= 3:
            stats["suspicious_lines"].append(record)

    ranked = []
    for preparer, stats in preparer_stats.items():
        if stats["total"] == 0:
            continue
        score = (
            stats["large_rounded"] * 2
            + stats["rounded"] * 0.5
            + stats["weekend"]
            + stats["dup_key"]
        )
        ranked.append((score, preparer, stats))

    ranked.sort(reverse=True, key=lambda x: x[0])

    account_suspicion = defaultdict(lambda: {"count": 0, "amount": 0.0, "preparers": Counter()})
    for record in records:
        amount = record.get("AbsoluteAmount")
        if amount is None:
            continue
        if is_rounded(amount) and p95 is not None and amount >= p95:
            acct = record.get("GLAccountNumber")
            acct_name = record.get("GLAccountName")
            key = f"{acct} - {acct_name}" if acct_name else str(acct)
            entry = account_suspicion[key]
            entry["count"] += 1
            entry["amount"] += amount
            entry["preparers"][record.get("PreparerID")] += 1

    top_accounts = sorted(account_suspicion.items(), key=lambda x: x[1]["amount"], reverse=True)[:10]

    visuals_dir = output_path.parent / "fraud_visuals"
    visuals_dir.mkdir(exist_ok=True)

    benford_labels = [str(d) for d in range(1, 10)]
    benford_actual = [benford.actual_pct.get(d, 0) * 100 for d in range(1, 10)]
    benford_expected = [benford.expected.get(d, 0) * 100 for d in range(1, 10)]
    write_grouped_bar_svg(
        visuals_dir / "benford_vs_expected.svg",
        "Benford's Law: Actual vs Expected (%)",
        benford_labels,
        {"Actual %": benford_actual, "Expected %": benford_expected},
        ["#4c78a8", "#f58518"],
    )

    top_preparer_labels = [entry[1] for entry in ranked[:10]]
    top_preparer_scores = [entry[0] for entry in ranked[:10]]
    write_bar_svg(
        visuals_dir / "top_preparer_scores.svg",
        "Top Preparer Risk Scores (Heuristic)",
        top_preparer_labels,
        top_preparer_scores,
        color="#54a24b",
    )

    with output_path.open("w", encoding="utf-8") as f:
        f.write("# Fraud Analysis Report\n\n")
        f.write("## Visual Summary\n")
        f.write("![Benford chart](fraud_visuals/benford_vs_expected.svg)\n\n")
        f.write("![Preparer risk scores](fraud_visuals/top_preparer_scores.svg)\n\n")
        f.write("## Data Summary\n")
        f.write(f"- Total journal line items: {len(records)}\n")
        f.write(f"- 95th percentile absolute amount: {p95:,.2f}\n")
        f.write(f"- 99th percentile absolute amount: {p99:,.2f}\n\n")

        f.write("## Benford's Law Check (Leading Digit Distribution)\n")
        f.write("| Digit | Actual % | Expected % | Count |\n")
        f.write("| --- | --- | --- | --- |\n")
        for digit in range(1, 10):
            actual = benford.actual_pct.get(digit, 0) * 100
            expected = benford.expected.get(digit, 0) * 100
            count = benford.counts.get(digit, 0)
            f.write(f"| {digit} | {actual:0.2f}% | {expected:0.2f}% | {count} |\n")
        f.write("\n")

        f.write("## Highest-Risk Preparers (Heuristic Ranking)\n")
        f.write("Scoring combines large rounded entries, rounded entries, weekend postings, and duplicate postings.\n\n")
        f.write("| Rank | Preparer | Score | Total Entries | Rounded | Large Rounded (>=95th pct) | Weekend | Duplicate Amount+Account+Date |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for idx, (score, preparer, stats) in enumerate(ranked[:10], start=1):
            f.write(
                f"| {idx} | {preparer} | {score:0.1f} | {stats['total']} | {stats['rounded']} | {stats['large_rounded']} | {stats['weekend']} | {stats['dup_key']} |\n"
            )
        f.write("\n")

        f.write("## Accounts with Large Rounded Entries (>=95th percentile)\n")
        f.write("| Account | Count | Total Amount | Top Preparers |\n")
        f.write("| --- | --- | --- | --- |\n")
        for account, stats in top_accounts:
            top_preparers = ", ".join([f"{p} ({c})" for p, c in stats["preparers"].most_common(3)])
            f.write(f"| {account} | {stats['count']} | {stats['amount']:,.2f} | {top_preparers} |\n")
        f.write("\n")

        f.write("## Example High-Risk Lines (Score >= 3)\n")
        f.write("| Preparer | Account | Account Name | Entry Date | Amount | Description | Source |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        example_rows = []
        for _, preparer, stats in ranked[:5]:
            for record in stats["suspicious_lines"][:5]:
                example_rows.append(record)
        for record in example_rows[:20]:
            entry_date = record.get("EntryDate")
            entry_date_str = entry_date.date().isoformat() if entry_date else ""
            f.write(
                "| {preparer} | {account} | {name} | {date} | {amount:,.2f} | {desc} | {source} |\n".format(
                    preparer=record.get("PreparerID"),
                    account=record.get("GLAccountNumber"),
                    name=record.get("GLAccountName"),
                    date=entry_date_str,
                    amount=record.get("AbsoluteAmount") or 0,
                    desc=(record.get("JEDescription") or "").strip(),
                    source=(record.get("Source") or "").strip(),
                )
            )


if __name__ == "__main__":
    build_report(Path("je_samples (1).xlsx"), Path("fraud_report.md"))
