"""
Report generation (spec section 22) — PDF via ReportLab, plus CSV and JSON
exports of the same diagnostic run.
"""
import csv
import json
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

STYLES = getSampleStyleSheet()
TITLE_STYLE = ParagraphStyle("NDTitle", parent=STYLES["Title"], textColor=colors.HexColor("#0b3d24"))
HEADING_STYLE = ParagraphStyle("NDHeading", parent=STYLES["Heading2"], spaceBefore=14, spaceAfter=6)
BODY_STYLE = STYLES["BodyText"]


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    table = Table(rows, colWidths=[5.5 * cm, 10 * cm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#374151")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
    ]))
    return table


def generate_pdf(run, user, output_path: str) -> str:
    r = run.result_json
    source = (
        "Simulated (DEMO MODE)" if r.get("simulated") is True
        else "Real measurements" if r.get("simulated") is False
        else "Unspecified (legacy record)"
    )
    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    elements = [
        Paragraph("NETDOCTOR", TITLE_STYLE),
        Paragraph("Network Diagnostic Report", STYLES["Heading3"]),
        Spacer(1, 6),
        Paragraph(f"Measurement source: {source}", BODY_STYLE),
        Paragraph(f"User: {user.email}", BODY_STYLE),
        Paragraph(f"Date/time: {run.created_at}", BODY_STYLE),
        Spacer(1, 10),

        Paragraph("Connectivity", HEADING_STYLE),
        _kv_table([
            ("Gateway", "Reachable" if r['gateway']['reachable'] else "ICMP unavailable / unreachable"),
            ("Internet", "Reachable" if r['internet']['reachable'] else "Unreachable"),
        ]),

        Paragraph("Latency", HEADING_STYLE),
        _kv_table([
            ("Min", f"{r['latency']['min_ms']} ms"), ("Average", f"{r['latency']['avg_ms']} ms"),
            ("Max", f"{r['latency']['max_ms']} ms"), ("Jitter", f"{r['latency']['jitter_ms']} ms"),
        ]),

        Paragraph("Packet Loss", HEADING_STYLE),
        _kv_table([
            ("Sent", str(r['packet_loss']['sent'])), ("Received", str(r['packet_loss']['received'])),
            ("Loss", "Unavailable (ICMP received no replies)"
             if r['packet_loss'].get('icmp_unavailable') else f"{r['packet_loss']['loss_pct']}%"),
        ]),

        Paragraph("DNS", HEADING_STYLE),
        _kv_table([
            ("Domain", r['dns']['domain']), ("Resolved IP", str(r['dns']['resolved_ip'])),
            ("Response time", f"{r['dns']['response_ms']} ms"),
        ]),

        Paragraph("Health Score", HEADING_STYLE),
        Paragraph(
            f"{run.health_score} / 100 — application-defined diagnostic indicator, "
            "not an industry-standard network health metric.", BODY_STYLE
        ),

        Paragraph("Findings", HEADING_STYLE),
    ]
    for f in r.get("findings", []):
        elements.append(Paragraph(f"<b>[{f['severity'].upper()}]</b> {f['text']}", BODY_STYLE))
        elements.append(Spacer(1, 4))

    elements.append(Paragraph("Recommendations", HEADING_STYLE))
    for rec in r.get("recommendations", []):
        elements.append(Paragraph(f"• {rec}", BODY_STYLE))

    if r.get("websites"):
        elements.append(Paragraph("HTTP Tests", HEADING_STYLE))
        rows = [["URL", "Status", "Response"]] + [
            [w["url"], str(w.get("status_code") or "unreachable"), f"{w.get('response_ms') or '—'} ms"]
            for w in r["websites"]
        ]
        wtable = Table(rows, colWidths=[8 * cm, 3 * cm, 3 * cm])
        wtable.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
        ]))
        elements.append(wtable)

    doc.build(elements)
    return output_path


def generate_csv(run, output_path: str) -> str:
    r = run.result_json
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["field", "value"])
        writer.writerow([
            "measurement_source",
            "simulated_demo_mode" if r.get("simulated") is True
            else "real_measurements" if r.get("simulated") is False
            else "unspecified_legacy_record",
        ])
        writer.writerow(["created_at", run.created_at])
        writer.writerow(["health_score", run.health_score])
        writer.writerow(["gateway_reachable", r["gateway"]["reachable"]])
        writer.writerow(["internet_reachable", r["internet"]["reachable"]])
        writer.writerow(["latency_min_ms", r["latency"]["min_ms"]])
        writer.writerow(["latency_avg_ms", r["latency"]["avg_ms"]])
        writer.writerow(["latency_max_ms", r["latency"]["max_ms"]])
        writer.writerow(["jitter_ms", r["latency"]["jitter_ms"]])
        writer.writerow([
            "packet_loss_pct",
            None if r["packet_loss"].get("icmp_unavailable") else r["packet_loss"]["loss_pct"],
        ])
        writer.writerow(["dns_domain", r["dns"]["domain"]])
        writer.writerow(["dns_response_ms", r["dns"]["response_ms"]])
        writer.writerow([])
        writer.writerow(["websites_url", "status_code", "response_ms"])
        for w in r.get("websites", []):
            writer.writerow([w["url"], w.get("status_code"), w.get("response_ms")])
        writer.writerow([])
        writer.writerow(["finding_severity", "finding_text"])
        for finding in r.get("findings", []):
            writer.writerow([finding["severity"], finding["text"]])
    return output_path


def generate_json(run, output_path: str) -> str:
    payload = {
        "id": run.id, "created_at": run.created_at.isoformat(), "health_score": run.health_score,
        "result": run.result_json,
    }
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return output_path
