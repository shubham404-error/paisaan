"""Session-friendly watchlist validation and portable JSON serialization."""
from __future__ import annotations

from copy import deepcopy


MAX_WATCHLIST_ITEMS = 20
EXPORT_VERSION = 1


class WatchlistError(ValueError):
    """A safe, user-facing watchlist validation error."""


def default_watchlists() -> dict:
    return {"active": "My watchlist", "lists": {"My watchlist": []}}


def normalize_watchlists(payload: object, valid_symbols: set[str] | None = None) -> dict:
    """Validate portable state and discard malformed, duplicate, or unavailable symbols."""
    if not isinstance(payload, dict) or not isinstance(payload.get("lists"), dict):
        raise WatchlistError("This watchlist file is not valid.")
    lists: dict[str, list[str]] = {}
    for raw_name, raw_symbols in payload["lists"].items():
        name = _name(raw_name)
        if name in lists or not isinstance(raw_symbols, list):
            raise WatchlistError("This watchlist file contains an invalid list.")
        symbols: list[str] = []
        for raw_symbol in raw_symbols:
            symbol = str(raw_symbol).strip().upper()
            if symbol and symbol not in symbols and (valid_symbols is None or symbol in valid_symbols):
                symbols.append(symbol)
        if len(symbols) > MAX_WATCHLIST_ITEMS:
            raise WatchlistError(f"{name} has more than {MAX_WATCHLIST_ITEMS} stocks.")
        lists[name] = symbols
    if not lists:
        return default_watchlists()
    active = payload.get("active")
    return {"active": active if active in lists else next(iter(lists)), "lists": lists}


def create_watchlist(state: dict, name: str) -> dict:
    result = deepcopy(state)
    clean_name = _name(name)
    if clean_name in result["lists"]:
        raise WatchlistError("A watchlist with that name already exists.")
    result["lists"][clean_name] = []
    result["active"] = clean_name
    return result


def add_to_watchlist(state: dict, name: str, symbols: list[str], valid_symbols: set[str]) -> dict:
    result = deepcopy(state)
    if name not in result["lists"]:
        raise WatchlistError("Choose an existing watchlist.")
    additions = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip().upper() in valid_symbols]
    current = result["lists"][name]
    merged = current + [symbol for symbol in additions if symbol not in current]
    if len(merged) > MAX_WATCHLIST_ITEMS:
        remaining = MAX_WATCHLIST_ITEMS - len(current)
        raise WatchlistError(f"{name} can hold up to {MAX_WATCHLIST_ITEMS} stocks; {remaining} slot(s) remain.")
    result["lists"][name] = merged
    result["active"] = name
    return result


def remove_from_watchlist(state: dict, name: str, symbols: list[str]) -> dict:
    result = deepcopy(state)
    if name not in result["lists"]:
        raise WatchlistError("Choose an existing watchlist.")
    remove = {str(symbol).strip().upper() for symbol in symbols}
    result["lists"][name] = [symbol for symbol in result["lists"][name] if symbol not in remove]
    return result


def export_watchlists(state: dict) -> dict:
    return {"version": EXPORT_VERSION, **state}


def _name(value: object) -> str:
    name = str(value).strip()
    if not 1 <= len(name) <= 40:
        raise WatchlistError("Watchlist names must be 1 to 40 characters.")
    return name
