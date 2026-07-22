import io
import os
import re

import numpy as np
import pandas as pd
import streamlit as st

from utils.funnel_ratios import build_ratios, percent_change

st.set_page_config(page_title="Funnel Comparison Pivot", page_icon="📊", layout="wide")
st.title("Funnel comparison pivot")

# ----------------------------------------------------------------------------
# Column config
# ----------------------------------------------------------------------------
UTM_COLS = ["utm source", "utm medium", "utm campaign", "utm term"]

# Event file (File 1) flags -> the deeper funnel steps
EVENT_FLAGS = {
    "Checkout Started": "checkout_started",
    "Address Landed": "address_landed",
    "Payment Step Reached": "payment_reached",
    "Payment Method Selected": "payment_selected",
    "Sessions Converted": "converted",
}

# Hourly file (File 2) -> Sessions / A2C / completed checkout
HOURLY_COLS = {
    "Sessions": "sessions",
    "Sessions with cart additions": "a2c",
    # "Sessions that completed checkout": "checkout_completed",
}

# Consistent count column order used throughout
ORDERED_COUNT_COLS = [
    "sessions",
    "a2c",
    # "checkout_completed",
    "checkout_started",
    "address_landed",
    "payment_reached",
    "payment_selected",
    "converted",
]

# ----------------------------------------------------------------------------
# Loading helpers
# ----------------------------------------------------------------------------
def file_type_check(name):
    _, extension = os.path.splitext(name)
    return extension.lower()


def _clean_col(c):
    """Strip whitespace, BOM, and non-breaking spaces from a column name."""
    return (
        str(c)
        .replace("\ufeff", "")
        .replace("\xa0", " ")
        .strip()
    )


def resolve_date_col(columns, wanted):
    """
    Find the intended date/hour column even if it's slightly off.

    Match order:
      1. exact
      2. case-insensitive exact
      3. case-insensitive 'contains' (e.g. 'Hour of Day', 'Date Hour')
    Returns the matched column name, or None.
    """
    cols = list(columns)
    lower = {c.lower(): c for c in cols}

    if wanted in cols:
        return wanted
    if wanted.lower() in lower:
        return lower[wanted.lower()]
    candidates = [c for c in cols if wanted.lower() in c.lower()]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _norm(name):
    """Normalize a column name for tolerant matching: lowercase, and collapse
    runs of whitespace / underscores / hyphens into a single space."""
    return re.sub(r"[\s_\-]+", " ", str(name).strip().lower())

def date_format(date):
    return date.strftime("%d-%b")

def resolve_metric_col(columns, wanted):
    """
    Resolve an expected metric name (e.g. 'Sessions with cart additions') to the
    actual column present in the file, tolerant of case, spacing, and separators.

    Match order:
      1. normalized exact
      2. normalized 'contains' (either direction), only if unambiguous
    Returns the actual column name, or None if no confident match.
    """
    norm_to_actual = {}
    for c in columns:
        norm_to_actual.setdefault(_norm(c), c)

    target = _norm(wanted)
    if target in norm_to_actual:
        return norm_to_actual[target]

    candidates = [
        actual
        for norm, actual in norm_to_actual.items()
        if target in norm or norm in target
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def build_metric_map(columns, expected):
    """
    Given the file's columns and an {source_name: output_name} dict, return
    {output_name: actual_column_or_None} by resolving each source name.
    """
    return {
        output: resolve_metric_col(columns, source)
        for source, output in expected.items()
    }


def to_numeric_counts(series):
    """
    Coerce a column of counts to numbers before summing. Handles thousands
    separators ('1,234') and stray text; anything unparseable becomes 0.
    """
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


@st.cache_data(show_spinner=False)
def load_raw(file_bytes, file_name):
    """Read the file to a DataFrame and clean column names (no date parsing yet)."""
    extension = file_type_check(file_name)
    buffer = io.BytesIO(file_bytes)
    if extension in (".xlsx", ".xls"):
        df = pd.read_excel(buffer)
    else:
        df = pd.read_csv(buffer)
    df.columns = [_clean_col(c) for c in df.columns]
    return df


def attach_date(df, date_col):
    """Parse date_col into a __date column. Assumes date_col already resolved to exist."""
    df = df.copy()
    df["__date"] = pd.to_datetime(
        df[date_col], errors="coerce", format="mixed"
    ).dt.date
    return df


def prepare_df(file, wanted_date_col, label):
    """
    Load a file, resolve its date column (with a fallback picker on mismatch),
    and attach __date. Returns a DataFrame or stops the app with diagnostics.
    """
    df = load_raw(file.getvalue(), file.name)
    df.columns = df.columns.str.lower()
    resolved = resolve_date_col(df.columns, wanted_date_col)

    if resolved is None:
        st.error(
            f"Could not find a '{wanted_date_col}' column in the {label} "
            f"('{file.name}'). Pick the correct column below."
        )
        st.caption(f"Columns detected in {label}:")
        st.code(", ".join(repr(c) for c in df.columns))
        resolved = st.selectbox(
            f"Date column for {label}",
            options=list(df.columns),
            key=f"datecol_{label}",
        )

    df = attach_date(df, resolved)

    # Surface unparseable dates rather than silently dropping them.
    n_bad = df["__date"].isna().sum()
    if n_bad:
        st.warning(
            f"{label}: {n_bad} row(s) in column '{resolved}' could not be "
            f"parsed as dates and will be excluded."
        )
    return df


def truthy(series):
    """Interpret event flags as 1/0 whether they are booleans, Y/N, 1/0, or timestamps."""
    if series.dtype == bool:
        return series.astype(int)
    s = series.astype(str).str.strip().str.lower()
    truthy_vals = {"1", "true", "yes", "y", "t"}
    out = s.isin(truthy_vals).astype(int)
    # Treat any non-empty, non-false, non-zero value (e.g. a timestamp) as truthy
    nonempty = ~s.isin({"", "nan", "none", "0", "false", "no", "n", "f"})
    out = (out | nonempty.astype(int)).clip(upper=1)
    return out


# ----------------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------------
def apply_utm_filters(df, filters):
    for col, vals in filters.items():
        if vals and col in df.columns:
            df = df[df[col].astype(str).isin(vals)]
    return df


def aggregate(
    df_gk: pd.DataFrame,
    df_shopify: pd.DataFrame,
    group_col: str,
    date_start,
    date_end,
    filters: dict,
    event_map: dict,
    hourly_map: dict,
) -> pd.DataFrame:
    """
    event_map  : {output_col: actual_gk_column_or_None} for the funnel-step flags
    hourly_map : {output_col: actual_sh_column_or_None} for the Shopify metrics
    Both are resolved once (see build_metric_map) and passed in so the same
    mapping is used for every date range and is visible to the diagnostics.
    """

    # ------------------------------------------------------------------
    # Filter by date
    # ------------------------------------------------------------------
    gk = df_gk.loc[
        (df_gk["__date"] >= date_start) & (df_gk["__date"] <= date_end)
    ].copy()

    sh = df_shopify.loc[
        (df_shopify["__date"] >= date_start) & (df_shopify["__date"] <= date_end)
    ].copy()

    # ------------------------------------------------------------------
    # Apply UTM filters
    # ------------------------------------------------------------------
    gk = apply_utm_filters(gk, filters)
    sh = apply_utm_filters(sh, filters)

    # ------------------------------------------------------------------
    # Ensure grouping column exists
    # ------------------------------------------------------------------
    if group_col not in gk.columns:
        raise KeyError(f"{group_col} not found in Event file.")
    if group_col not in sh.columns:
        raise KeyError(f"{group_col} not found in Shopify file.")

    gk[group_col] = gk[group_col].fillna("(blank)")
    sh[group_col] = sh[group_col].fillna("(blank)")

    # ------------------------------------------------------------------
    # Build event-step counts from the Gokwik file.
    # If the resolved source column is numeric (already per-row counts),
    # sum it directly; otherwise treat it as a per-session flag (0/1).
    # ------------------------------------------------------------------
    for output_col, actual_col in event_map.items():
        if actual_col is not None and actual_col in gk.columns:
            source = gk[actual_col]
            numeric = pd.to_numeric(
                source.astype(str).str.replace(",", "", regex=False),
                errors="coerce",
            )
            if numeric.notna().mean() >= 0.9:
                # Mostly numeric -> real counts; sum the values as-is.
                gk[output_col] = numeric.fillna(0)
            else:
                # Flags / Y-N / timestamps -> presence means "1".
                gk[output_col] = truthy(source)
        else:
            gk[output_col] = 0

    event_cols = list(event_map.keys())

    gk_agg = (
        gk.groupby(group_col, dropna=False)[event_cols]
        .sum()
        .astype(int)
    )

    # ------------------------------------------------------------------
    # Build Shopify metric counts. Coerce to numbers before summing so
    # text values like "1,234" are added, not string-concatenated.
    # ------------------------------------------------------------------
    for output_col, actual_col in hourly_map.items():
        if actual_col is not None and actual_col in sh.columns:
            sh[output_col] = to_numeric_counts(sh[actual_col])
        else:
            sh[output_col] = 0

    shopify_cols = list(hourly_map.keys())

    sh_agg = sh.groupby(group_col, dropna=False)[shopify_cols].sum()

    # ------------------------------------------------------------------
    # Merge both datasets
    # ------------------------------------------------------------------
    combined = sh_agg.join(gk_agg, how="outer").fillna(0)

    # Keep columns in a consistent order
    for col in ORDERED_COUNT_COLS:
        if col not in combined.columns:
            combined[col] = 0

    combined = combined[ORDERED_COUNT_COLS]
    combined = combined.astype(int)
    combined = combined.sort_index()

    return combined


# ----------------------------------------------------------------------------
# Styling
# ----------------------------------------------------------------------------
def style_pct(df):
    return df.style.format("{:.2f}%", na_rep="-").set_properties(
        **{"text-align": "right"}
    )


def style_diff(df):
    def color(v):
        if pd.isna(v):
            return ""
        if v > 0:
            return "background-color: #c6efce; color: #006100;"
        if v < 0:
            return "background-color: #ffc7ce; color: #9c0006;"
        return "background-color: #f2f2f2;"

    return (
        df.style.format("{:.2f}%", na_rep="-")
        .map(color)
        .set_properties(**{"text-align": "right"})
    )


def with_total_row(counts: pd.DataFrame) -> pd.DataFrame:
    """Append a 'Total' row holding the column sums, for display/debugging."""
    out = counts.copy()
    out.loc["Total"] = counts.sum()
    return out.astype(int)


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
col1, col2 = st.columns([2, 2])

with col1:
    gk_file = st.file_uploader(
        "Upload Gokwik Checkout Funnel with Marketing Params",
        type=["csv", "xlsx"]
        
        
    )

with col2:
    shopify_file = st.file_uploader(
        "Upload Shopify Sessions File",
        type=["csv", "xlsx"]
    )

if not gk_file or not shopify_file:
    st.stop()

gk_df = prepare_df(gk_file, "Date", "Event file")
shopify_df = prepare_df(shopify_file, "Day", "Shopify Hourly file")

# ----------------------------------------------------------------------------
# Resolve which real column feeds each metric (done once, tolerant matching)
# ----------------------------------------------------------------------------
event_map = build_metric_map(gk_df.columns, EVENT_FLAGS)      # gk file
hourly_map = build_metric_map(shopify_df.columns, HOURLY_COLS)  # shopify file

missing = (
    [out for out, actual in event_map.items() if actual is None]
    + [out for out, actual in hourly_map.items() if actual is None]
)


# Grouping column
present_utm = [c for c in UTM_COLS if c in gk_df.columns and c in shopify_df.columns]
if not present_utm:
    st.error("No shared UTM columns found across both files.")
    st.stop()

# Date bounds (needed to build the date pickers)
all_dates = sorted(
    d for d in set(gk_df["__date"].dropna()) | set(shopify_df["__date"].dropna())
)
if not all_dates:
    st.error("No valid dates parsed from either file.")
    st.stop()
dmin, dmax = all_dates[0], all_dates[-1]

# ----------------------------------------------------------------------------
# Parameters form
# Everything the user selects lives inside a form, so the app does NOT rerun
# (and does NOT recompute) until "Run comparison" is pressed.
# ----------------------------------------------------------------------------
with st.form("params"):
    default_group = "utm campaign" if "utm campaign" in present_utm else present_utm[0]
    group_col = st.selectbox(
        "Group rows by",
        present_utm,
        index=present_utm.index(default_group),
    )

    st.subheader("UTM filters")
    fcols = st.columns(len(present_utm))
    filters = {}
    for i, col in enumerate(present_utm):
        with fcols[i]:
            opts = sorted(
                set(gk_df[col].dropna().astype(str))
                | set(shopify_df[col].dropna().astype(str))
            )
            default = []
            low = {o.lower(): o for o in opts}
            if col == "utm source" and "affiliate" in low:
                default = [low["affiliate"]]
            if col == "utm medium" and "partnerships" in low:
                default = [low["partnerships"]]
            filters[col] = st.multiselect(col, opts, default=default, key=f"f_{col}")

    st.subheader("Comparison ranges")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**Range A (later / current)**")
        a_range = st.date_input(
            "Range A", value=(dmin, dmax), min_value=dmin, max_value=dmax, key="ra"
        )
    with r2:
        st.markdown("**Range B (earlier / baseline)**")
        b_range = st.date_input(
            "Range B", value=(dmin, dmax), min_value=dmin, max_value=dmax, key="rb"
        )

    submitted = st.form_submit_button("Run comparison", type="primary")

if not submitted:
    st.info(
        "Choose your grouping, UTM filters, and both date ranges, "
        "then click **Run comparison**."
    )
    st.stop()

# ----------------------------------------------------------------------------
# Validate ranges
# ----------------------------------------------------------------------------
if not (
    isinstance(a_range, tuple)
    and len(a_range) == 2
    and isinstance(b_range, tuple)
    and len(b_range) == 2
):
    st.error("Pick a start and end date for both ranges, then run again.")
    st.stop()

a_start, a_end = a_range
b_start, b_end = b_range
a_days = (a_end - a_start).days + 1
b_days = (b_end - b_start).days + 1

if a_days != b_days:
    st.error(
        f"Ranges must cover the same number of days for a like-to-like comparison. "
        f"Range A = {a_days} days, Range B = {b_days} days."
    )
    st.stop()

st.caption(f"Comparing {a_days} days vs {b_days} days.")

# ----------------------------------------------------------------------------
# Compute
# ----------------------------------------------------------------------------
counts_a = aggregate(
    gk_df, shopify_df, group_col, a_start, a_end, filters, event_map, hourly_map
)
counts_b = aggregate(
    gk_df, shopify_df, group_col, b_start, b_end, filters, event_map, hourly_map
)

ratios_a = build_ratios(counts_a)
ratios_b = build_ratios(counts_b)

# Align rows for the difference grid (Total pinned to the bottom)
idx = sorted(set(ratios_a.index) | set(ratios_b.index))
if "Total" in idx:
    idx.remove("Total")
    idx.append("Total")

ratios_a = ratios_a.reindex(idx)
ratios_b = ratios_b.reindex(idx)
diff = percent_change(ratios_b, ratios_a)

# ----------------------------------------------------------------------------
# Display
# ----------------------------------------------------------------------------
st.subheader("% change (Range A vs Range B, relative to B)")
st.dataframe(style_diff(diff), use_container_width=True)

st.subheader(f"Range A: {a_start} → {a_end}")
st.dataframe(style_pct(ratios_a), use_container_width=True)

st.subheader(f"Range B: {b_start} → {b_end}")
st.dataframe(style_pct(ratios_b), use_container_width=True)


# with st.expander("Show raw counts (debug)", expanded=True):
#     st.caption(
#         "Counts feeding the ratios. Column order is the funnel order: "
#         "sessions → a2c → checkout_started → "
#         "address_landed → payment_reached → payment_selected → converted."
#     )

#     st.markdown(f"**Counts A — {a_start} → {a_end}**")
#     st.dataframe(with_total_row(counts_a), use_container_width=True)

#     st.markdown(f"**Counts B — {b_start} → {b_end}**")
#     st.dataframe(with_total_row(counts_b), use_container_width=True)

# ----------------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------------


buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as xl:
    diff.to_excel(xl, sheet_name="Difference")
    ratios_a.to_excel(xl, sheet_name=f"Funnel% — {date_format(a_start)}-{date_format(a_end)}")
    ratios_b.to_excel(xl, sheet_name=f"Funnel% — {date_format(b_start)}-{date_format(b_end)}")
    counts_a.to_excel(xl, sheet_name=f"Funnel Counts — {date_format(a_start)}-{date_format(a_end)}")
    counts_b.to_excel(xl, sheet_name=f"Funnel Counts — {date_format(b_start)}-{date_format(b_end)}")
buf.seek(0)
st.download_button(
    "⬇️ Download all sheets (xlsx)",
    data=buf,
    file_name="funnel_comparison.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)