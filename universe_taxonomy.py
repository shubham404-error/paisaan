"""Transparent, local classifications for the active Nifty 200 universe.

The official constituent feed gives us company and industry labels.  This module
adds only narrow, auditable business tags that are needed to make natural-language
screens deterministic.  It is deliberately a taxonomy, not a source of prices or
fundamentals.
"""
from __future__ import annotations

import re


_PRIVATE_BANKS = {
    "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "FEDERALBNK",
    "IDFCFIRSTB", "INDUSINDBK", "RBLBANK", "YESBANK", "BANDHANBNK",
}
_PUBLIC_BANKS = {"SBIN", "PNB", "BANKBARODA", "CANBK", "UNIONBANK", "INDIANB", "BANKINDIA", "CENTRALBK"}
_TAG_ALIASES = {
    "private_bank": ("private bank", "private banks", "private banking"),
    "public_sector_bank": ("public sector bank", "public sector banks", "psu bank", "psu banks", "government bank", "government banks"),
    "bank": ("bank", "banks", "banking"),
    "information_technology": ("information technology", "technology", "it sector", "software"),
    "healthcare": ("healthcare", "pharma", "pharmaceutical", "pharmaceuticals", "hospital", "hospitals"),
    "automobile": ("automobile", "automobiles", "auto sector", "autos"),
    "financial_services": ("financial services", "financial sector"),
}


def taxonomy_records(rows: list[dict]) -> list[dict[str, object]]:
    """Attach stable local tags to verified constituent records."""
    records: list[dict[str, object]] = []
    for row in rows:
        symbol = str(row.get("Symbol", "")).upper()
        company = str(row.get("Company", ""))
        industry = str(row.get("Industry", ""))
        normalized_industry = re.sub(r"[^a-z0-9]+", "_", industry.lower()).strip("_")
        tags = {normalized_industry} if normalized_industry else set()
        industry_lower = industry.lower()
        company_lower = company.lower()
        if symbol in _PRIVATE_BANKS:
            tags.update({"bank", "private_bank", "financial_services"})
        elif symbol in _PUBLIC_BANKS:
            tags.update({"bank", "public_sector_bank", "financial_services"})
        elif "bank" in company_lower:
            tags.update({"bank", "financial_services"})
        if "information technology" in industry_lower or "software" in industry_lower:
            tags.add("information_technology")
        if any(term in industry_lower for term in ("health", "pharma", "hospital")):
            tags.add("healthcare")
        if any(term in industry_lower for term in ("automobile", "auto")):
            tags.add("automobile")
        if "financial" in industry_lower:
            tags.add("financial_services")
        records.append({"Symbol": symbol, "Company": company, "Industry": industry, "tags": sorted(tags)})
    return records


def deterministic_scope(query: str, records: list[dict[str, object]]) -> tuple[list[str], str | None]:
    """Resolve explicit, supported business-group wording without relying on an LLM sample."""
    text = f" {query.lower()} "
    matched_tags = [tag for tag, aliases in _TAG_ALIASES.items() if any(re.search(rf"\b{re.escape(alias)}\b", text) for alias in aliases)]
    # Every official Industry label is also usable in plain language without adding a
    # bespoke code path for each sector (for example, "chemicals" or "consumer goods").
    all_tags = {str(tag) for record in records for tag in record["tags"]}
    for tag in all_tags:
        phrase = tag.replace("_", " ")
        if len(phrase) >= 3 and re.search(rf"\b{re.escape(phrase)}\b", text):
            matched_tags.append(tag)
    if not matched_tags:
        return [], None
    # Choose the most specific tag (private/public bank before bank/financial services).
    specificity = {"private_bank": 3, "public_sector_bank": 3, "bank": 2, "information_technology": 2, "healthcare": 2, "automobile": 2, "financial_services": 1}
    selected_tag = max(matched_tags, key=lambda tag: specificity.get(tag, 2))
    symbols = [str(record["Symbol"]) for record in records if selected_tag in set(record["tags"])]
    return symbols, selected_tag.replace("_", " ")
