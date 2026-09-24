"""
Auto-Generated ESG & CSR Donation Report — Feature 9
Generates a professional PDF sustainability report using ReportLab.

IMPORTANT DISCLAIMER:
This is a system-generated sustainability report intended for internal
tracking and awareness. It has NOT been audited, certified, or validated
for official ESG / CSR / tax / legal compliance purposes.
Results labelled ESTIMATED are computational approximations, not
scientifically measured values.

Reports are saved to:  reports/<institution>_<timestamp>.pdf
"""

from __future__ import annotations

import os
import re
import io
from datetime import datetime
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Optional ReportLab import — fail gracefully
# ──────────────────────────────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")

DISCLAIMER = (
    "DISCLAIMER: This is a system-generated sustainability report for internal "
    "awareness and tracking purposes only. Values labelled ESTIMATED are "
    "computational approximations derived from published emission and water "
    "withdrawal factors (Poore & Nemecek, 2018). This document has not been "
    "audited, certified, or validated for official ESG, CSR, tax, or legal "
    "compliance. Do not present ESTIMATED figures as scientifically measured values."
)

METHODOLOGY_NOTE = (
    "Methodology: CO2e estimates use the median food-system emission factor of "
    "1.6 kg CO2e per kg food (median of 43 food products, Poore & Nemecek 2018, "
    "Science 360:6392; verified from datasets/Food_Production.csv). Water savings "
    "use 417.1 liters per kg food (median freshwater withdrawal, 38 products with "
    "data, same source; verified). Meal counts derived from reported records or "
    "estimated at 0.5 kg per meal (WHO/FSSAI institutional norm)."
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _safe_str(value: Any, default: str = "Not provided") -> str:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def _safe_date(value: Any) -> str:
    if not value:
        return "Not specified"
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%d %B %Y")
        except ValueError:
            continue
    return s  # return as-is if unparseable


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", str(text))[:40]


def _ensure_reports_dir() -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)


def _output_path(institution: str) -> str:
    _ensure_reports_dir()
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug  = _slug(institution) if institution else "institution"
    fname = f"{slug}_{ts}.pdf"
    return os.path.join(REPORTS_DIR, fname)


# ──────────────────────────────────────────────────────────────────────────────
# PDF builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_pdf(data: dict, path: str) -> None:
    """Build and save the PDF to `path` using ReportLab."""
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    W = A4[0] - 4 * cm  # usable width

    # ── Custom styles ──────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        spaceAfter=6,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1a5276"),
    )
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=4,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#5d6d7e"),
    )
    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        spaceBefore=12,
        spaceAfter=4,
        textColor=colors.HexColor("#1a5276"),
        borderPad=2,
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=14,
        spaceAfter=4,
    )
    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=11,
        textColor=colors.HexColor("#7f8c8d"),
        spaceAfter=4,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#555555"),
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("BhojanSetu — System-Generated Sustainability Report", title_style))
    story.append(Paragraph(
        _safe_str(data.get("institution_name"), "Institution Name Not Provided"),
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1a5276")))
    story.append(Spacer(1, 0.3 * cm))

    # Report meta
    meta_rows = [
        ["Reporting Period:",
         f"{_safe_date(data.get('reporting_period_start'))} "
         f"to {_safe_date(data.get('reporting_period_end'))}"],
        ["Generated On:", datetime.now().strftime("%d %B %Y, %H:%M")],
        ["Report Type:", "System-generated sustainability summary"],
    ]
    meta_table = Table(meta_rows, colWidths=[4 * cm, W - 4 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1a5276")),
        ("VALIGN",    (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Key Metrics ────────────────────────────────────────────────────────
    story.append(Paragraph("Key Sustainability Metrics", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aed6f1")))
    story.append(Spacer(1, 0.2 * cm))

    def _fmt_float(v: Any, decimals: int = 2, suffix: str = "") -> str:
        try:
            return f"{float(v):,.{decimals}f}{suffix}"
        except (TypeError, ValueError):
            return "N/A"

    metric_rows = [
        ["Metric", "Value", "Notes"],
        ["Food Redistributed",
         _fmt_float(data.get("food_redistributed_kg"), suffix=" kg"),
         "Total food successfully redistributed to recipients"],
        ["Food Waste Avoided",
         _fmt_float(data.get("food_waste_avoided_kg"), suffix=" kg"),
         "Food diverted from waste stream"],
        ["Meals Redistributed",
         _fmt_float(data.get("meals_redistributed"), 0),
         "Estimated number of meals provided"],
        ["CO2e Avoided (ESTIMATED)",
         _fmt_float(data.get("estimated_co2e_avoided_kg"), suffix=" kg CO2e"),
         "ESTIMATED — see methodology note"],
        ["Water Saved (ESTIMATED)",
         _fmt_float(data.get("estimated_water_saved_liters"), suffix=" L"),
         "ESTIMATED — see methodology note"],
    ]

    metric_table = Table(
        metric_rows,
        colWidths=[4.5 * cm, 4.5 * cm, W - 9 * cm],
        repeatRows=1,
    )
    metric_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a5276")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        # Data rows
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),
         [colors.HexColor("#eaf4fc"), colors.white]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#aed6f1")),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # Value column
        ("FONTNAME",      (1, 1), (1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",     (1, 1), (1, -1), colors.HexColor("#1a5276")),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Sustainability Trend ───────────────────────────────────────────────
    trend_series = data.get("sustainability_trend", [])
    if trend_series:
        story.append(Paragraph("Sustainability Trend", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aed6f1")))
        story.append(Spacer(1, 0.2 * cm))

        trend_rows = [["Date", "Food Redistributed (kg)", "Food Waste Avoided (kg)"]]
        for point in trend_series:
            trend_rows.append([
                _safe_str(point.get("date")),
                _fmt_float(point.get("food_redistributed_kg"), suffix=" kg"),
                _fmt_float(point.get("food_waste_avoided_kg", ""), suffix=" kg"),
            ])

        trend_table = Table(
            trend_rows,
            colWidths=[3.5 * cm, 5 * cm, 5 * cm],
            repeatRows=1,
        )
        trend_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a5276")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("ALIGN",         (1, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1),
             [colors.HexColor("#eaf4fc"), colors.white]),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#aed6f1")),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ]))
        story.append(trend_table)
        story.append(Spacer(1, 0.4 * cm))

    # ── Donation / Exchange Records ────────────────────────────────────────
    donation_records = data.get("donation_records", [])
    if donation_records:
        story.append(Paragraph("Donation & Exchange Records", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aed6f1")))
        story.append(Spacer(1, 0.2 * cm))

        don_rows = [["Date", "Recipient / Partner", "Quantity (kg)", "Notes"]]
        for rec in donation_records:
            don_rows.append([
                _safe_str(rec.get("date")),
                _safe_str(rec.get("recipient") or rec.get("ngo_name") or rec.get("partner")),
                _fmt_float(rec.get("quantity_kg"), suffix=" kg"),
                _safe_str(rec.get("notes") or rec.get("status"), default="—"),
            ])

        col_w = [3 * cm, W - 11 * cm, 3 * cm, 3 * cm]
        don_table = Table(don_rows, colWidths=col_w, repeatRows=1)
        don_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1a5276")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1),
             [colors.HexColor("#eaf4fc"), colors.white]),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#aed6f1")),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("ALIGN",         (2, 1), (2, -1), "RIGHT"),
        ]))
        story.append(don_table)
        story.append(Spacer(1, 0.4 * cm))

    # ── Production Planning Highlights ────────────────────────────────────
    planning_recs = data.get("production_planning_recommendations", [])
    if planning_recs:
        story.append(Paragraph("Production Planning Recommendations", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aed6f1")))
        story.append(Spacer(1, 0.2 * cm))
        for i, pr in enumerate(planning_recs, 1):
            story.append(Paragraph(
                f"<b>{i}. {_safe_str(pr.get('recommendation'))}</b>",
                body_style,
            ))
            story.append(Paragraph(
                f"  Reason: {_safe_str(pr.get('reason'))}",
                label_style,
            ))
            ev = pr.get("evidence", {})
            if ev:
                story.append(Paragraph(
                    f"  Evidence: {ev.get('surplus_occurrences','?')} occurrences in "
                    f"{ev.get('total_surplus_records_analysed','?')} records "
                    f"({ev.get('date_range','N/A')}). Confidence: {pr.get('confidence','?')}",
                    label_style,
                ))
            story.append(Spacer(1, 0.15 * cm))
        story.append(Spacer(1, 0.2 * cm))

    # ── Methodology Note ──────────────────────────────────────────────────
    story.append(Paragraph("Methodology Note", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aed6f1")))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(METHODOLOGY_NOTE, disclaimer_style))
    story.append(Spacer(1, 0.3 * cm))

    # ── Disclaimer ────────────────────────────────────────────────────────
    story.append(Paragraph("Important Disclaimer", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aed6f1")))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(DISCLAIMER, disclaimer_style))
    story.append(Spacer(1, 0.5 * cm))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(
        f"Generated by BhojanSetu AI Platform · {datetime.now().strftime('%d %B %Y')} · "
        "System-generated report — not an official compliance document",
        ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=7,
            leading=10,
            textColor=colors.HexColor("#aaaaaa"),
            alignment=TA_CENTER,
        ),
    ))

    doc.build(story)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_report(data: dict, output_path: str | None = None) -> str:
    """
    Generate a PDF sustainability report.

    Parameters
    ----------
    data : dict
        Report data. Recognised keys:
          institution_name, reporting_period_start, reporting_period_end,
          food_redistributed_kg, food_waste_avoided_kg, meals_redistributed,
          estimated_co2e_avoided_kg, estimated_water_saved_liters,
          donation_records (list of dicts),
          sustainability_trend (list of dicts),
          production_planning_recommendations (list of dicts)
    output_path : str or None
        Full path to write PDF. If None, auto-generated under reports/.

    Returns
    -------
    str  — absolute path to the generated PDF file.

    Raises
    ------
    ImportError if reportlab is not installed.
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError(
            "reportlab is required for PDF generation. "
            "Install with:  pip install reportlab"
        )

    if output_path is None:
        institution = _safe_str(data.get("institution_name"), "institution")
        output_path = _output_path(institution)

    _build_pdf(data, output_path)
    return output_path
