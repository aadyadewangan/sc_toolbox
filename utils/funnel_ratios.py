"""
funnel_utils.py
---------------
Reusable calculation helpers for the funnel comparison app.

Keeping these here (rather than inline in the Streamlit script) means the
core math can be read, edited, and unit-tested on its own, without touching
any UI code.

Three functions:
    safe_divide     -> element-wise division returning percentages, 0-safe
    build_ratios    -> turns a counts table into the funnel ratio table
    percent_change  -> relative % difference between two ratio tables
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# The order ratio columns should always appear in.
# Defined once here so build_ratios and any caller can rely on it.
# ---------------------------------------------------------------------------
RATIO_COLUMN_ORDER = [
    "A2C/Sessions",
    "Checkout/A2C",
    "Address/Checkout",
    "Payment Initiated/Address",
    "Payment Selected/Initiated",
    "Conversion/Payment",
    "CR wrt Checkout",
    "CR wrt Sessions",
]


def safe_divide(numerator, denominator):
    """
    Safely divide two Series/arrays and return percentages.
    Returns NaN where the denominator is zero.
    """
    numerator = numerator.astype(float)
    denominator = denominator.astype(float)
    return np.where(
        denominator != 0,
        (numerator / denominator) * 100,
        np.nan,
    )


def build_ratios(counts: pd.DataFrame) -> pd.DataFrame:

    ratios = pd.DataFrame(index=counts.index)

    # -------------------------------------------------------------
    # Funnel Ratios
    # -------------------------------------------------------------
    ratios["A2C/Sessions"] = safe_divide(
        counts["a2c"],
        counts["sessions"],
    )
    ratios["Checkout/A2C"] = safe_divide(
        counts["checkout_started"],
        counts["a2c"],
    )
    ratios["Address/Checkout"] = safe_divide(
        counts["address_landed"],
        counts["checkout_started"],
    )
    ratios["Payment Initiated/Address"] = safe_divide(
        counts["payment_reached"],
        counts["address_landed"],
    )
    ratios["Payment Selected/Initiated"] = safe_divide(
        counts["payment_selected"],
        counts["payment_reached"],
    )
    ratios["Conversion/Payment"] = safe_divide(
        counts["converted"],
        counts["payment_selected"],
    )
    ratios["CR wrt Checkout"] = safe_divide(
        counts["converted"],
        counts["checkout_started"],
    )
    ratios["CR wrt Sessions"] = safe_divide(
        counts["converted"],
        counts["sessions"],
    )

    # -------------------------------------------------------------
    # Total Row
    # -------------------------------------------------------------
    totals = counts.sum()
    ratios.loc["Total"] = {
        "A2C/Sessions":
            (totals["a2c"] / totals["sessions"] * 100)
            if totals["sessions"] else np.nan,
        "Checkout/A2C":
            (totals["checkout_started"] / totals["a2c"] * 100)
            if totals["a2c"] else np.nan,
        "Address/Checkout":
            (totals["address_landed"] / totals["checkout_started"] * 100)
            if totals["checkout_started"] else np.nan,
        "Payment Initiated/Address":
            (totals["payment_reached"] / totals["address_landed"] * 100)
            if totals["address_landed"] else np.nan,
        "Payment Selected/Initiated":
            (totals["payment_selected"] / totals["payment_reached"] * 100)
            if totals["payment_reached"] else np.nan,
        "Conversion/Payment":
            (totals["converted"] / totals["payment_selected"] * 100)
            if totals["payment_selected"] else np.nan,
        "CR wrt Checkout":
            (totals["converted"] / totals["checkout_started"] * 100)
            if totals["checkout_started"] else np.nan,
        "CR wrt Sessions":
            (totals["converted"] / totals["sessions"] * 100)
            if totals["sessions"] else np.nan,
    }

    # -------------------------------------------------------------
    # Column Order
    # -------------------------------------------------------------
    ratios = ratios[RATIO_COLUMN_ORDER]
    return ratios


def percent_change(new: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    
    new = new.astype(float)
    old = old.astype(float)

    # Turn any zero baseline into NaN so the division produces NaN there
    # rather than inf / a divide-by-zero warning.
    baseline = old.where(old != 0)

    return (new - old) / baseline * 100