"""
SGX announcement category codes for api.sgx.com filtering.

==============================================================================
                            !!! UNVERIFIED !!!
==============================================================================
The category codes below are PLACEHOLDERS based on observed announcement
titles. They MUST be verified against live api.sgx.com responses before the
first production scraper run.

VERIFICATION STEPS (do these in a browser, save the output to this file):

  1. Open https://www.sgx.com/securities/company-announcements in Chrome.
  2. Open DevTools (F12) -> Network tab -> filter to "Fetch/XHR".
  3. Reload the page. Find the request to api.sgx.com/announcements/v1.0/...
  4. Inspect the JSON response. Each announcement carries fields like:
       - "category"            <-- one-line description, may be human readable
       - "sub_category"        <-- finer-grained
       - "headlineCategoryId"  <-- the stable internal code (if present)
       - "headline"            <-- the announcement title
  5. Filter the UI by each category in the SGX dropdown. Each filter sends
     a new request with a "cat" or similar query parameter -- THAT is the
     code to pin here.
  6. Replace each TODO_VERIFY value below with the real code.
  7. Tick the verification box on the relevant Stage 1 carry-over item in
     MARKET_EXPANSION_CHECKLIST.md.

ESCAPE HATCH: if the api exposes only human-readable categories with no
stable code, replace the dict values with substring patterns and switch
sgxnet_fetcher.SGXNetFetcher.dispatch() from equality to substring match.
The fetcher already supports both modes via the MATCH_MODE constant.
==============================================================================
"""

# Base API endpoint. Confirmed via Towards Data Science article (2019)
# and Singapore-investor open-source code as of 2024-2025. No auth header.
API_BASE = "https://api.sgx.com/announcements/v1.0/"

# How dispatcher should compare announcement payload field to these codes.
# "exact"     -> announcement["category"] == CODE
# "substring" -> CODE in announcement["headline"].lower()
# Set to "substring" until exact codes are verified.
MATCH_MODE = "substring"

# Which field in the announcement payload to match against.
MATCH_FIELD = "headline"  # change to "category" once exact codes confirmed

# -----------------------------------------------------------------------------
# Section 1 — Disclosure of Interests
# -----------------------------------------------------------------------------
# In substring mode the matcher is tolerant -- "changes in interest" catches
# all of: Form 1 (initial), Form 3 (changes), Form 4 (cessation).
DI_CATEGORIES = {
    "disclosure_of_interest": "disclosure of interest",  # TODO_VERIFY exact code
    "change_in_interest":     "changes in interest",      # TODO_VERIFY exact code
}

# -----------------------------------------------------------------------------
# Section 2 — Corporate Actions
# -----------------------------------------------------------------------------
CA_CATEGORIES = {
    # Daily Share Buy-Back Notice (Appendix 8D)
    "share_buyback":          "share buy-back",           # TODO_VERIFY
    # Mandate renewal / AGM circulars
    "buyback_mandate":        "share buyback mandate",    # TODO_VERIFY
    "agm_circular":           "notice of annual general meeting",  # TODO_VERIFY
    # Equity issuances
    "placement":              "placement",                # TODO_VERIFY
    "rights_issue":           "rights issue",             # TODO_VERIFY
    "bonus_issue":            "bonus issue",              # TODO_VERIFY
    "scrip_dividend":         "scrip dividend",           # TODO_VERIFY (SG-specific)
    "convertible_securities": "convertible",              # TODO_VERIFY
    # Results
    "financial_statements":   "financial statements",     # TODO_VERIFY
}

# -----------------------------------------------------------------------------
# Section 3 — Capital Market
# -----------------------------------------------------------------------------
# Most CM data does NOT come from api.sgx.com -- it comes from the static
# CSV downloads on sgx.com/research-education/. Listed here for completeness
# of the routing table.
CM_SOURCES = {
    "daily_short_sell_url":   "https://www.sgx.com/research-education/securities",
    # SBL eligibility list URL must be inspected; currently a placeholder.
    "sbl_eligibility_url":    None,  # TODO_VERIFY
}

# -----------------------------------------------------------------------------
# Combined routing table -- used by SGXNetFetcher.dispatch()
# -----------------------------------------------------------------------------
ROUTING = {
    **{k: ("di", v) for k, v in DI_CATEGORIES.items()},
    **{k: ("corp_actions", v) for k, v in CA_CATEGORIES.items()},
}


def is_verified() -> bool:
    """Quick programmatic check used by the scrapers in --strict mode.

    Returns False as long as any TODO_VERIFY remains in this file.
    The scrapers should refuse to run in production until this returns True.
    """
    return False  # flip to True only after all TODO_VERIFY items resolved
