"""Session-friendly watchlist validation and portable JSON serialization."""
from __future__ import annotations

import base64
from copy import deepcopy
import json
import zlib


MAX_WATCHLIST_ITEMS = 20
EXPORT_VERSION = 1
SHARE_VERSION = 1
MAX_SHARE_PAYLOAD_CHARS = 2048
MAX_SHARE_JSON_BYTES = 4096


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


def encode_shared_watchlist(name: str, symbols: list[str]) -> str:
    """Create a compact URL-safe snapshot of one watchlist; no identity is included."""
    clean_name = _name(name)
    clean_symbols = _symbols(symbols)
    packet = {"v": SHARE_VERSION, "n": clean_name, "s": clean_symbols}
    raw = json.dumps(packet, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, level=9)).decode("ascii").rstrip("=")


def decode_shared_watchlist(payload: object, valid_symbols: set[str]) -> tuple[str, list[str]]:
    """Validate a URL payload and retain only symbols in the live Nifty 200 universe."""
    if not isinstance(payload, str) or not payload or len(payload) > MAX_SHARE_PAYLOAD_CHARS:
        raise WatchlistError("This shared watchlist link is not valid.")
    try:
        padded = payload + "=" * (-len(payload) % 4)
        compressed = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, MAX_SHARE_JSON_BYTES + 1)
        if inflater.unconsumed_tail or not inflater.eof or len(raw) > MAX_SHARE_JSON_BYTES:
            raise ValueError
        packet = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, zlib.error):
        raise WatchlistError("This shared watchlist link is not valid.") from None
    if not isinstance(packet, dict) or packet.get("v") != SHARE_VERSION:
        raise WatchlistError("This shared watchlist link uses an unsupported format.")
    if set(packet) != {"v", "n", "s"}:
        raise WatchlistError("This shared watchlist link is not valid.")
    name = _name(packet["n"])
    symbols = [symbol for symbol in _symbols(packet["s"]) if symbol in valid_symbols]
    if not symbols:
        raise WatchlistError("This shared watchlist has no stocks in the current Nifty 200 universe.")
    return name, symbols


def import_shared_watchlist(state: dict, payload: object, valid_symbols: set[str]) -> dict:
    """Add a shared snapshot as a local editable copy with a collision-safe name."""
    name, symbols = decode_shared_watchlist(payload, valid_symbols)
    result = deepcopy(state)
    imported_name = _unique_name(result["lists"], f"{name} (shared)")
    result["lists"][imported_name] = symbols
    result["active"] = imported_name
    return result


def _symbols(values: object) -> list[str]:
    if not isinstance(values, list):
        raise WatchlistError("This watchlist contains invalid stocks.")
    symbols: list[str] = []
    for raw_symbol in values:
        if not isinstance(raw_symbol, str):
            raise WatchlistError("This watchlist contains invalid stocks.")
        symbol = raw_symbol.strip().upper()
        if not symbol:
            raise WatchlistError("This watchlist contains invalid stocks.")
        if symbol not in symbols:
            symbols.append(symbol)
    if not symbols or len(symbols) > MAX_WATCHLIST_ITEMS:
        raise WatchlistError(f"A watchlist must contain 1 to {MAX_WATCHLIST_ITEMS} stocks.")
    return symbols


def _unique_name(lists: dict, suggested: str) -> str:
    base = suggested[:40].rstrip() or "Shared watchlist"
    if base not in lists:
        return base
    number = 2
    while True:
        suffix = f" ({number})"
        candidate = f"{base[:40 - len(suffix)].rstrip()}{suffix}"
        if candidate not in lists:
            return candidate
        number += 1


def _name(value: object) -> str:
    name = str(value).strip()
    if not 1 <= len(name) <= 40:
        raise WatchlistError("Watchlist names must be 1 to 40 characters.")
    return name
