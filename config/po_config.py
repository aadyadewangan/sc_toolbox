# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------
GST_RATE = 0.18                       # flat 18%, shown as a single GST line
GST_LINE_LABEL = "GST"                # change to "GST (18%)" if you want the rate shown

# PO number = PO_NUMBER_PREFIX + <partner code> + <brand code> + DDMMYYYY
# e.g. "PO" + "PTM" + "MC" + "28062026" -> "POPTMMC28062026"
PO_NUMBER_PREFIX = "PO"

# Campaign name = f(partner_name, month).  Edit CAMPAIGN_NAME_FORMAT to restyle.
# Available fields: {partner}, {month} (full month name), {yy} (2-digit year),
# {yyyy} (4-digit year).  Default renders "Paytm July '26".
CAMPAIGN_NAME_FORMAT = "{partner} {month} '{yy}"

# Where signature PNGs live (referenced per-brand below, path relative to the app).
ASSETS_DIR = "assets"


# ---------------------------------------------------------------------------
# Internal brands (the "Advertiser" side of the PO)
# ---------------------------------------------------------------------------
BRANDS = {
    "mCaffeine": {
        "code": "MC",
        "legal_name": "PEP TECHNOLOGIES PRIVATE LIMITED",
        "billing_address": (
            "A Wing, 304, Boomerang Business Park, Kanakia Chandivali Road, "
            "Yadav Nagar, Mumbai, Maharashtra, 400072"
        ),
        "pan": "AAICP2804J",
        "gstin": "27AAICP2804J2ZB",
        "contact_name": "Shreyansh Tanna",
        "phone": "7977115945",
        "emails": ["shreyansh.tanna@mcaffeine.com", "priyansu.mohapatra@mcaffeine.com"],
        # Signatory block at the bottom of the PO
        "signatory_name": "Shreyansh Tanna",
        "signatory_designation": "Manager - Growth Marketing",
        "signature_png": "signature_shreyansh.png",   # inside ASSETS_DIR
    },
    "Hyphen": {
        "code": "HYP",
        "legal_name": "Kreative Beauty Private Limited",
        "billing_address": (
            "A Wing, 304, Boomerang Business Park, Kanakia Chandivali Road, "
            "Yadav Nagar, Mumbai, Maharashtra, 400072"
        ),
        "pan": "AAJCK9697F",
        "gstin": "27AAJCK9697F1ZS",
        "contact_name": "Shreyansh Tanna",
        "phone": "7977115945",
        "emails": ["shreyansh.tanna@mcaffeine.com", "priyansu.mohapatra@mcaffeine.com"],
        "signatory_name": "Shreyansh Tanna",
        "signatory_designation": "Manager - Growth Marketing",
        "signature_png": "signature_shreyansh.png",
    },
}


# ---------------------------------------------------------------------------
# Partners (the "Publisher" side of the PO)
# Leave any field blank ("") if it does not apply - the template tolerates
# missing publisher details (as in the Zepto sample).
# ---------------------------------------------------------------------------
PARTNERS = {
    "Paytm": {
        "code": "PTM",
        "publisher_name": "ONE97 COMMUNICATIONS LIMITED",
        "billing_address": (
            "Plot No H-10B, Skymark One, Tower D, Sector 98, Noida, "
            "Gautambuddha Nagar, Uttar Pradesh, 201304"
        ),
        "pan": "AAACO4007A",
        "gstin": "09AAACO4007A1Z3",
        "contact_name": "Akshita Wadhwa",
        "phone": "9654327448",
        "emails": ["akshita.wadhwa@paytm.com", "mohit3.k@paytm.com"],
        # Default ad-unit label used when adding a line item for this partner
        "default_ad_unit": "Paytm",
    },
    "Zepto": {
        "code": "ZPT",
        "publisher_name": "",
        "billing_address": "",
        "pan": "",
        "gstin": "",
        "contact_name": "Shreya Hooda",
        "phone": "9910264824",
        "emails": ["shreya.hooda@zepto.com"],
        "default_ad_unit": "Zepto Rewards",
    },

    "Zomato": {
        "code": "ZMT",
        "publisher_name": "",
        "billing_address": "",
        "pan": "",
        "gstin": "",
        "contact_name": "Disha Seth",
        "phone": "8875346498",
        "emails": ["disha.seth@zomato.com"],
        "default_ad_unit": "Zomato Rewards",
    },
}


# ---------------------------------------------------------------------------
# Commercial models
#   per_unit = True  -> amount auto-computes as rate * volume (/ divisor)
#   per_unit = False -> amount is entered manually (e.g. Fixed ROAS)
#   unit             -> suffix shown in the deliverable label, e.g. "15rs"
#   divisor          -> for CPM-style pricing (rate per 1000)
# ---------------------------------------------------------------------------
COMMERCIAL_MODELS = {
    "Per Engagement": {"per_unit": True, "unit": "rs", "divisor": 1},
    "CPC": {"per_unit": True, "unit": "", "divisor": 1},
    "CPM": {"per_unit": True, "unit": "", "divisor": 1000},
    "Fixed ROAS": {"per_unit": False, "unit": "", "divisor": 1},
    "Fixed Fee": {"per_unit": False, "unit": "", "divisor": 1},
}

DEFAULT_OBJECTIVE = "Code Distribution"