import calendar
import datetime as dt
import os

import pandas as pd
import streamlit as st

import config.po_config as cfg
from utils.po_utils import build_po, build_po_pdf, inr

st.set_page_config(page_title="PO Generator", page_icon="🧾", layout="wide")
st.title("Purchase Order generator")

MONTHS = list(calendar.month_name)[1:]  # ['January', ..., 'December']


# ---------------------------------------------------------------------------
# 1. Brand + partner
# ---------------------------------------------------------------------------
c1, c2 = st.columns(2)
with c1:
    brand_key = st.selectbox("Internal brand (Advertiser)", list(cfg.BRANDS))
with c2:
    partner_key = st.selectbox("Partner (Publisher)", list(cfg.PARTNERS))

if not cfg.PARTNERS[partner_key]["publisher_name"]:
    st.caption(
        f"Note: no publisher details configured for {partner_key} - "
        "the Publisher column will render blank."
    )

# ---------------------------------------------------------------------------
# 2. Dates, campaign month, payment terms
# ---------------------------------------------------------------------------
today = dt.date.today()

c3, c4, c5 = st.columns(3)
with c3:
    order_date = st.date_input("Order date (drives PO number)", value=today)
with c4:
    start_date = st.date_input("Campaign start", value=today)
with c5:
    end_date = st.date_input("Campaign end", value=today + dt.timedelta(days=30))

c6, c7, c8 = st.columns(3)
with c6:
    campaign_month = st.selectbox(
        "Campaign name month", MONTHS, index=start_date.month - 1
    )
with c7:
    campaign_year = st.number_input(
        "Campaign name year", min_value=2020, max_value=2100,
        value=start_date.year, step=1,
    )
with c8:
    payment_terms = st.number_input(
        "Payment terms (days)", min_value=0, max_value=365, value=30, step=1
    )

if end_date < start_date:
    st.error("Campaign end date is before the start date.")
    st.stop()

# ---------------------------------------------------------------------------
# 3. Line items (commercial model, inventory, budget)
# ---------------------------------------------------------------------------
st.subheader("Line items")
st.caption(
    "Amount auto-computes as rate x volume for per-unit models "
    "(Per Engagement, CPC, CPM). Leave 'Amount override' blank to auto-compute, "
    "or fill it to set the amount manually (e.g. Fixed ROAS)."
)

default_ad_unit = cfg.PARTNERS[partner_key].get("default_ad_unit", partner_key)
starter = pd.DataFrame(
    [
        {
            "objective": cfg.DEFAULT_OBJECTIVE,
            "placement": "Scratch cards",
            "ad_unit": default_ad_unit,
            "model": "Per Engagement",
            "rate": 15.0,
            "total_codes": 84000.0,
            "amount_override": None,
        }
    ]
)

edited = st.data_editor(
    starter,
    num_rows="dynamic",
    use_container_width=True,
    key="po_line_items",
    column_config={
        "objective": st.column_config.TextColumn("Objective"),
        "placement": st.column_config.TextColumn("Placement (inventory)"),
        "ad_unit": st.column_config.TextColumn("Ad Unit"),
        "model": st.column_config.SelectboxColumn(
            "Commercial model", options=list(cfg.COMMERCIAL_MODELS), required=True
        ),
        "rate": st.column_config.NumberColumn("Rate", format="%.2f"),
        "total_codes": st.column_config.NumberColumn("Total codes / volume", format="%.0f"),
        "amount_override": st.column_config.NumberColumn(
            "Amount override (blank = auto)", format="%.0f"
        ),
    },
)

raw_items = edited.to_dict("records")
raw_items = [r for r in raw_items if (r.get("model") or r.get("placement") or r.get("rate"))]
if not raw_items:
    st.info("Add at least one line item to continue.")
    st.stop()

# ---------------------------------------------------------------------------
# 4. Signature
# ---------------------------------------------------------------------------
brand_sig = os.path.join(cfg.ASSETS_DIR, cfg.BRANDS[brand_key].get("signature_png", ""))
signature_path = brand_sig if os.path.exists(brand_sig) else None

uploaded_sig = None
if signature_path is None:
    st.warning(
        f"Signature image not found at '{brand_sig}'. Drop the PNG there for it to "
        "appear automatically, or upload one below for this PO."
    )
    up = st.file_uploader("Signature PNG (optional, this PO only)", type=["png"])
    if up is not None:
        tmp = os.path.join(".", f"_sig_{brand_key}.png")
        with open(tmp, "wb") as f:
            f.write(up.getvalue())
        signature_path = tmp
        uploaded_sig = tmp

# ---------------------------------------------------------------------------
# 5. Build + preview
# ---------------------------------------------------------------------------
po = build_po(
    brand_key=brand_key,
    partner_key=partner_key,
    order_date=order_date,
    campaign_month=MONTHS.index(campaign_month) + 1,
    campaign_year=int(campaign_year),
    start_date=start_date,
    end_date=end_date,
    payment_term_days=payment_terms,
    raw_line_items=raw_items,
    signature_path=signature_path,
)

st.subheader("Preview")
p1, p2, p3 = st.columns(3)
p1.metric("PO number", po["po_number"])
p2.metric("Campaign", po["campaign_name"])
p3.metric("Duration", po["duration_label"])

preview_rows = [
    {
        "Objective": li["objective"],
        "Placement": li["placement"],
        "Ad Unit": li["ad_unit"],
        "Deliverable": li["deliverable"],
        "Total codes": inr(li["total_codes"]) if li["total_codes"] else "",
        "Amount (INR)": inr(li["amount"]),
    }
    for li in po["line_items"]
]
st.table(pd.DataFrame(preview_rows))

t1, t2, t3 = st.columns(3)
t1.metric("Total (Exc GST)", inr(po["total_ex_gst"]))
t2.metric(f"{po['gst_label']} @ {int(cfg.GST_RATE * 100)}%", inr(po["gst"]))
t3.metric("Total", inr(po["total"]))

# ---------------------------------------------------------------------------
# 6. Generate PDF
# ---------------------------------------------------------------------------
mmmyy = f"{calendar.month_abbr[MONTHS.index(campaign_month) + 1]}{str(campaign_year)[-2:]}"

brand_short = "" 
if brand_key == "mCaffeine":
    brand_short = "mCaff"
elif brand_key == "Hyphen":
    brand_short = "HYP"

if st.button("Generate PO PDF", type="primary"):
    pdf_bytes = build_po_pdf(po)
    st.download_button(
        "⬇️ Download PO",
        data=pdf_bytes,
        file_name=f"{brand_short}-{partner_key}-{mmmyy}-{po['po_number']}.pdf",
        mime="application/pdf",
    )
    st.success(f"Generated PO")

    if uploaded_sig and os.path.exists(uploaded_sig):
        os.remove(uploaded_sig)