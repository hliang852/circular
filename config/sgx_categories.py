"""
SGX announcement category codes for api.sgx.com filtering.

==============================================================================
                        VERIFIED 2026-05-25
==============================================================================
All codes below were confirmed against live api.sgx.com/announcements/v1.1/
responses on 2026-05-25.

VERIFICATION METHOD (DevTools-equivalent, performed via Python requests):
  1. Fetched https://www.sgx.com/config/appconfig.json to get the live
     endpoint URLs and CMS_VERSION.
  2. Fetched the CMS qrValidator token (ROT-13 obfuscated) from:
         CMS_API_URL/?queryId=<CMS_VERSION>:we_chat_qr_validator
  3. Called api.sgx.com/announcements/v1.1/company with the
     'authorizationToken' header, iterating over top-level cat codes
     ANNC / CACT / PLST / TRAD over a 3-month window.
  4. Recorded every (cat, sub, category_name) tuple observed.

RESPONSE FIELD MAP (verified against live items):
  item["id"]                     → announcement_id (stable internal ID)
  item["cat"]                    → top-level category  ("ANNC", "CACT", …)
  item["sub"]                    → subcategory code    ("ANNC13", "CACT18", …)
  item["category_name"]          → human-readable name
  item["title"]                  → announcement headline string
  item["issuers"][0]["stock_code"] → SGX stock ticker (e.g. "D05")
  item["issuer_name"]            → issuer display name
  item["broadcast_date_time"]    → Unix milliseconds (NOT a string)
  item["url"]                    → links.sgx.com PDF/filing URL
==============================================================================
"""

# ---------------------------------------------------------------------------
# Connection / auth
# ---------------------------------------------------------------------------

# Live endpoint confirmed from appconfig.json (v1.1, not v1.0)
API_BASE = "https://api.sgx.com/announcements/v1.1/"
API_COMPANY_ENDPOINT   = API_BASE + "company"     # main feed endpoint
API_SECURITYCODE_EP    = API_BASE + "securitycode" # per-ticker lookup

# CMS config (used to fetch the short-lived authorizationToken)
CMS_API_URL  = "https://api2.sgx.com/content-api"
CMS_VERSION  = "70f75ec90c030bab34d750ee55d74b016f70d4b6"
# Token URL pattern: CMS_API_URL + "/?queryId=" + CMS_VERSION + ":we_chat_qr_validator"
# Response: {"data": {"qrValidator": "<ROT-13-encoded-token>"}}
# Header to send: authorizationToken: <rot13_decoded_token>

# ---------------------------------------------------------------------------
# Dispatch mode — now uses the 'sub' field (exact subcategory code).
# ---------------------------------------------------------------------------
MATCH_MODE  = "exact"   # "exact" | "substring"
MATCH_FIELD = "sub"     # field on the Announcement dataclass to compare

# ---------------------------------------------------------------------------
# Section 1 — Disclosure of Interests
# ---------------------------------------------------------------------------
# sub=ANNC14 covers Form 1 (initial), Form 3 (change), Form 4 (cessation)
# because SGX groups all three into one subcategory.
DI_CATEGORIES = {
    "disclosure_of_interest": "ANNC14",  # "Disclosure of Interest/ Changes in Interest"
}

# ---------------------------------------------------------------------------
# Section 2 — Corporate Actions
# ---------------------------------------------------------------------------
CA_CATEGORIES = {
    # Daily Share Buy-Back Notice (Appendix 8D) — filed each trading day
    "share_buyback":          "ANNC13",  # "Share Buy Back-On Market"
    # AGM circular (includes share buyback mandate renewal each year)
    "agm_circular":           "ANNC05",  # "Annual General Meeting"
    # Equity issuances
    "placement":              "PLST05",  # "Listing-Equity" (allotment notice after placement)
    "rights_issue":           "CACT18",  # "Rights"
    "bonus_issue":            "CACT01",  # "Bonus Issue/ Capitalisation Issue"
    "scrip_dividend":         "CACT19",  # "Scrip Election/ Distribution/ DRP"
    "share_consolidation":    "CACT17",  # "Share Consolidation"
    # Results
    "financial_statements":   "ANNC17",  # "Financial Statements"
}

# Not mapped (out of scope for Circular v1 SG):
#   ANNC06  Asset Acquisitions and Disposals
#   ANNC11  Change of Catalist Sponsor
#   ANNC15  Employee Stock Option / Share Scheme
#   ANNC18  General Announcement
#   CACT02  Capital Distribution
#   CACT04  Capital Reduction
#   CACT06  Cash Dividend / Distribution
#   CACT07  Corporate Debt Restructuring
#   CACT10  Final Maturity
#   CACT15  Partial Redemption
#   CACT16  Repurchase Offer / Reverse Rights
#   CACT23  Issuer's Early Redemption (Call Option)
#   CACT25  Coupon Payment
#   PLST01  Change of Terms (warrants)
#   PLST03  Listing Confirmation
#   PLST08  Listing-Warrants
#   TRAD*   Trading halts, buying-in, delistings

# ---------------------------------------------------------------------------
# Section 3 — Capital Market (static downloads, not from announcements API)
# ---------------------------------------------------------------------------
CM_SOURCES = {
    "daily_short_sell_url":  "https://www.sgx.com/research-education/securities",
    # SBL eligibility list URL — inspect sgx.com/securities/securities-borrowing-lending
    "sbl_eligibility_url":   None,  # TODO_VERIFY (not blocking for v1 launch)
}

# ---------------------------------------------------------------------------
# Combined routing table — used by SGXNetFetcher._classify()
# ---------------------------------------------------------------------------
ROUTING = {
    **{k: ("di",           v) for k, v in DI_CATEGORIES.items()},
    **{k: ("corp_actions", v) for k, v in CA_CATEGORIES.items()},
}


def is_verified() -> bool:
    """Returns True now that all sub codes are confirmed against live data.

    Scrapers in --strict mode check this before running.
    Last verified: 2026-05-25 against api.sgx.com/announcements/v1.1/
    """
    return True
