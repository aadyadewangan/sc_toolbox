import calendar
import io
import math
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Image,
    Spacer,
)

import config.po_config as cfg


# ===========================================================================
# Formatting helpers
# ===========================================================================
def inr(value):
    """Format a number with comma grouping, matching the samples (1,260,000)."""
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return ""


def _fmt_rate(rate):
    """Render a rate without a trailing '.0' (15.0 -> '15', 1.8 -> '1.8')."""
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return str(rate)
    return str(int(r)) if r == int(r) else str(r)


# ===========================================================================
# Calculation logic
# ===========================================================================
def make_po_number(order_date, partner_key, brand_key):
    """PO_NUMBER_PREFIX + partner code + brand code + DDMMYYYY."""
    partner_code = cfg.PARTNERS[partner_key]["code"]
    brand_code = cfg.BRANDS[brand_key]["code"]
    return (
        f"{cfg.PO_NUMBER_PREFIX}{partner_code}{brand_code}"
        f"{order_date.strftime('%d%m%Y')}"
    )


def make_campaign_name(partner_key, month_number, year):
    """Compose the campaign name using CAMPAIGN_NAME_FORMAT."""
    month_full = calendar.month_name[month_number]   # 'July'
    month_abbr = calendar.month_abbr[month_number]   # 'Jul'
    return cfg.CAMPAIGN_NAME_FORMAT.format(
        partner=partner_key,
        month=month_full,
        mon=month_abbr,
        yy=f"{year % 100:02d}",
        yyyy=year,
    )


def make_duration_label(start, end):
    """'62 Days (1 Jul - 31 Aug)', counting both endpoints."""
    days = (end - start).days + 1
    return f"{days} Days ({start.day} {start.strftime('%b')} - {end.day} {end.strftime('%b')})"


def resolve_line_item(row):
    """
    Turn one raw line-item (dict from the editor) into the resolved form the
    PDF needs: composed deliverable label + effective amount.

    Raw keys: objective, placement, ad_unit, model, rate, total_codes,
              amount_override (None/NaN means auto)
    """
    model_name = row.get("model") or ""
    model = cfg.COMMERCIAL_MODELS.get(
        model_name, {"per_unit": False, "unit": "", "divisor": 1}
    )

    rate = row.get("rate") or 0
    volume = row.get("total_codes") or 0

    # Deliverable label, e.g. "Per Engagement (15rs)"
    unit = model["unit"]
    deliverable = f"{model_name} ({_fmt_rate(rate)}{unit})" if model_name else ""

    # Effective amount: override wins; else auto-compute for per-unit models.
    override = row.get("amount_override")
    has_override = override is not None and not (
        isinstance(override, float) and math.isnan(override)
    )
    if has_override:
        amount = float(override)
    elif model["per_unit"]:
        amount = float(rate) * float(volume) / model["divisor"]
    else:
        amount = 0.0  # non-per-unit model with no override -> user must fill it

    return {
        "objective": row.get("objective") or cfg.DEFAULT_OBJECTIVE,
        "placement": row.get("placement") or "",
        "ad_unit": row.get("ad_unit") or "",
        "deliverable": deliverable,
        "total_codes": float(volume) if volume else 0,
        "amount": amount,
    }


def compute_totals(resolved_items):
    total_ex_gst = sum(li["amount"] for li in resolved_items)
    gst = round(total_ex_gst * cfg.GST_RATE)
    total = total_ex_gst + gst
    return total_ex_gst, gst, total


def build_po(
    brand_key,
    partner_key,
    order_date,
    campaign_month,
    campaign_year,
    start_date,
    end_date,
    payment_term_days,
    raw_line_items,
    signature_path=None,
):
    """Assemble the full PO dict for the PDF generator."""
    brand = cfg.BRANDS[brand_key]
    partner = cfg.PARTNERS[partner_key]

    resolved = [resolve_line_item(r) for r in raw_line_items]
    total_ex_gst, gst, total = compute_totals(resolved)

    # Resolve the signature path: explicit override, else the brand's config asset.
    if signature_path is None:
        signature_path = os.path.join(cfg.ASSETS_DIR, brand.get("signature_png", ""))

    return {
        "order_date": order_date.strftime("%d-%b-%y") + "    ",
        "po_number": make_po_number(order_date, partner_key, brand_key),
        "advertiser": {
            "name": brand["legal_name"],
            "address": brand["billing_address"],
            "pan": brand["pan"],
            "gstin": brand["gstin"],
            "contact": brand["contact_name"],
            "phone": brand["phone"],
            "emails": brand["emails"],
        },
        "publisher": {
            "name": partner["publisher_name"],
            "address": partner["billing_address"],
            "pan": partner["pan"],
            "gstin": partner["gstin"],
            "contact": partner["contact_name"],
            "phone": partner["phone"],
            "emails": partner["emails"],
        },
        "brand_name": brand_key,
        "campaign_name": make_campaign_name(partner_key, campaign_month, campaign_year),
        "duration_label": make_duration_label(start_date, end_date),
        "payment_terms": f"{int(payment_term_days)} Days",
        "line_items": resolved,
        "total_ex_gst": total_ex_gst,
        "gst": gst,
        "gst_label": cfg.GST_LINE_LABEL,
        "total": total,
        "signatory": {
            "name": brand["signatory_name"],
            "designation": brand["signatory_designation"],
            "date": order_date.strftime("%d %B %Y"),
            "signature_path": signature_path,
        },
    }


# ===========================================================================
# PDF rendering
# ===========================================================================
_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=8, leading=10)
_BODY_BOLD = ParagraphStyle("body_bold", fontName="Helvetica-Bold", fontSize=8, leading=10)
_CENTER = ParagraphStyle("center", parent=_BODY, alignment=1)
_CENTER_BOLD = ParagraphStyle("center_bold", parent=_BODY_BOLD, alignment=1)
_RIGHT = ParagraphStyle("right", parent=_BODY, alignment=2)
_TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=11, leading=13, alignment=1)


def _p(text, style=_BODY):
    return Paragraph("" if text is None else str(text), style)


def _emails(emails):
    """Stack a list of emails on separate lines inside one cell."""
    if not emails:
        return _p("", _CENTER)
    return _p("<br/>".join(str(e) for e in emails), _CENTER)


def _grid(extra=None):
    """Shared border styling for every section table."""
    base = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    return TableStyle(base + (extra or []))

LABEL_COL = 0.2
def _table_top(po, W):
    col = [LABEL_COL * W, (0.50 - LABEL_COL) * W, 0.20 * W, 0.30 * W]
    data = [
        [_p("PURCHASE ORDER", _TITLE), "", "", ""],
        [
            _p("Order Date", _CENTER_BOLD),
            _p(po["order_date"], _CENTER),
            _p("Purchase Order Number", _CENTER_BOLD),
            _p(po["po_number"], _CENTER_BOLD),
        ],
    ]
    return Table(data, colWidths=col, style=_grid([("SPAN", (0, 0), (-1, 0))]))


def _table_parties(po, W):
    col = [0.20 * W, 0.40 * W, 0.40 * W]
    adv, pub = po["advertiser"], po["publisher"]
    data = [    
        [_p(""), _p("Advertiser information", _CENTER_BOLD), _p("Publisher Information", _CENTER_BOLD)],
        [_p("Name", _BODY_BOLD), _p(adv["name"], _CENTER), _p(pub["name"], _CENTER)],
        [_p("Billing Address", _BODY_BOLD), _p(adv["address"]), _p(pub["address"])],
        [_p("PAN", _BODY_BOLD), _p(adv["pan"], _CENTER), _p(pub["pan"], _CENTER)],
        [_p("GSTIN", _BODY_BOLD), _p(adv["gstin"], _CENTER), _p(pub["gstin"], _CENTER)],
        [_p("Contact Name", _BODY_BOLD), _p(adv["contact"], _CENTER), _p(pub["contact"], _CENTER)],
        [_p("Phone", _BODY_BOLD), _p(adv["phone"], _CENTER), _p(pub["phone"], _CENTER)],
        [_p("Email Id", _BODY_BOLD), _emails(adv["emails"]), _emails(pub["emails"])],
    ]
    return Table(data, colWidths=col, style=_grid([("VALIGN", (0, 0), (-1, -1), "TOP")]))


def _table_campaign(po, W):
    col = [0.30 * W, 0.70 * W]
    data = [
        [_p("Campaign Information", _CENTER_BOLD), ""],
        [_p("Brand name", _BODY_BOLD), _p(po["brand_name"], _CENTER)],
        [_p("Campaign Name", _BODY_BOLD), _p(po["campaign_name"], _CENTER)],
        [_p("Campaign duration", _BODY_BOLD), _p(po["duration_label"], _CENTER)],
        [_p("Payment Terms", _BODY_BOLD), _p(po["payment_terms"], _CENTER)],
    ]
    return Table(data, colWidths=col, style=_grid([("SPAN", (0, 0), (-1, 0))]))


def _table_lines(po, W):
    col = [0.16 * W, 0.13 * W, 0.11 * W, 0.24 * W, 0.16 * W, 0.20 * W]
    header = [
        _p("Objective", _CENTER_BOLD),
        _p("Placement", _CENTER_BOLD),
        _p("Ad Unit", _CENTER_BOLD),
        _p("Buy Type<br/>Deliverable", _CENTER_BOLD),
        _p("Total codes", _CENTER_BOLD),
        _p("Amount in INR", _CENTER_BOLD),
    ]
    data = [header]
    for li in po["line_items"]:
        data.append([
            _p(li["objective"], _CENTER),
            _p(li["placement"], _CENTER),
            _p(li["ad_unit"], _CENTER),
            _p(li["deliverable"], _CENTER),
            _p(inr(li["total_codes"]) if li["total_codes"] else "", _CENTER),
            _p(inr(li["amount"]), _CENTER),
        ])

    first_total_row = len(data)
    data.append(["", "", "", "", _p("Total (Exc GST)", _CENTER), _p(inr(po["total_ex_gst"]), _CENTER)])
    data.append(["", "", "", "", _p(po["gst_label"], _CENTER), _p(inr(po["gst"]), _CENTER)])
    data.append(["", "", "", "", _p("Total", _CENTER), _p(inr(po["total"]), _CENTER_BOLD)])

    style = _grid([
        ("SPAN", (0, first_total_row), (3, first_total_row)),
        ("SPAN", (0, first_total_row + 1), (3, first_total_row + 1)),
        ("SPAN", (0, first_total_row + 2), (3, first_total_row + 2)),
    ])
    return Table(data, colWidths=col, style=style)


def _signature_flowables(po):
    sig = po["signatory"]
    flow = [
        _p("FOR ADVERTISER -", _BODY_BOLD),
        Spacer(1, 4),
        _p(f"Name: {sig['name']}", _BODY_BOLD),
        _p(f"Designation: {sig['designation']}", _BODY_BOLD),
        _p(f"Date: {sig['date']}", _BODY_BOLD),
        _p("Signature:", _BODY_BOLD),
    ]
    path = sig.get("signature_path")
    if path and os.path.exists(path):
        try:
            img = Image(path)
            max_w = 3.2 * cm
            ratio = img.imageHeight / float(img.imageWidth)
            img.drawWidth = max_w
            img.drawHeight = max_w * ratio
            flow.append(Spacer(1, 2))
            flow.append(img)
        except Exception:
            pass
    return flow


def _table_signature(po, W):
    col = [0.28 * W, 0.72 * W]
    data = [[_signature_flowables(po), _p("")]]
    style = _grid([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 50),
    ])
    return Table(data, colWidths=col, rowHeights=[5 * cm], style=style)


def build_po_pdf(po: dict) -> bytes:
    """Render the PO dict to PDF and return the bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title=po.get("po_number", "Purchase Order"),
    )
    W = doc.width
    story = [
        _table_top(po, W),
        _table_parties(po, W),
        _table_campaign(po, W),
        _table_lines(po, W),
        _table_signature(po, W),
    ]
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()