"""The reference universe.

The demo market is synthetic but *internally consistent*: sector and market
benchmarks are computed from the same instruments a user watches, so a claim
like "NVDA outperformed semiconductors by 3.1%" is arithmetic, not decoration.

Everything here is static reference data. Prices live in `synthetic.py`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    exchange: str
    sector: str
    base_price: float
    # Annualised volatility, used to shape the synthetic path and to normalise
    # a move into "how unusual is this *for this stock*".
    annual_vol: float
    beta: float
    avg_daily_volume: int
    market_cap_b: float


SECTORS: dict[str, str] = {
    "SEMI": "Semiconductors",
    "TECH": "Technology",
    "FIN": "Financials",
    "ENERGY": "Energy",
    "AUTO": "Automotive",
    "HEALTH": "Healthcare",
    "CONSUMER": "Consumer",
}

MARKET_INDEX_NAME = "Broad Market"

_INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("NVDA", "NVIDIA Corporation", "NASDAQ", "SEMI", 171.42, 0.52, 1.72, 214_000_000, 4210.0),
    Instrument("AMD", "Advanced Micro Devices", "NASDAQ", "SEMI", 168.30, 0.55, 1.81, 62_000_000, 272.0),
    Instrument("AVGO", "Broadcom Inc.", "NASDAQ", "SEMI", 292.10, 0.41, 1.29, 28_000_000, 1360.0),
    Instrument("INTC", "Intel Corporation", "NASDAQ", "SEMI", 24.86, 0.46, 1.10, 88_000_000, 108.0),
    Instrument("TSM", "Taiwan Semiconductor ADR", "NYSE", "SEMI", 187.55, 0.38, 1.18, 31_000_000, 972.0),
    Instrument("AAPL", "Apple Inc.", "NASDAQ", "TECH", 232.18, 0.24, 1.05, 54_000_000, 3520.0),
    Instrument("MSFT", "Microsoft Corporation", "NASDAQ", "TECH", 428.75, 0.22, 0.94, 21_000_000, 3180.0),
    Instrument("GOOGL", "Alphabet Inc. Class A", "NASDAQ", "TECH", 194.62, 0.27, 1.02, 29_000_000, 2360.0),
    Instrument("META", "Meta Platforms Inc.", "NASDAQ", "TECH", 612.40, 0.33, 1.21, 15_000_000, 1550.0),
    Instrument("AMZN", "Amazon.com Inc.", "NASDAQ", "CONSUMER", 218.94, 0.29, 1.14, 41_000_000, 2290.0),
    Instrument("TSLA", "Tesla Inc.", "NASDAQ", "AUTO", 342.60, 0.58, 1.94, 96_000_000, 1090.0),
    Instrument("F", "Ford Motor Company", "NYSE", "AUTO", 11.24, 0.36, 1.31, 72_000_000, 44.0),
    Instrument("RIVN", "Rivian Automotive", "NASDAQ", "AUTO", 13.85, 0.71, 2.05, 38_000_000, 14.0),
    Instrument("JPM", "JPMorgan Chase & Co.", "NYSE", "FIN", 243.80, 0.21, 0.98, 9_000_000, 686.0),
    Instrument("GS", "Goldman Sachs Group", "NYSE", "FIN", 578.20, 0.24, 1.12, 2_400_000, 182.0),
    Instrument("V", "Visa Inc. Class A", "NYSE", "FIN", 312.45, 0.18, 0.87, 6_100_000, 604.0),
    Instrument("XOM", "Exxon Mobil Corporation", "NYSE", "ENERGY", 118.30, 0.25, 0.72, 17_000_000, 512.0),
    Instrument("CVX", "Chevron Corporation", "NYSE", "ENERGY", 156.72, 0.23, 0.68, 8_500_000, 288.0),
    Instrument("OXY", "Occidental Petroleum", "NYSE", "ENERGY", 47.15, 0.34, 0.96, 14_000_000, 44.0),
    Instrument("LLY", "Eli Lilly and Company", "NYSE", "HEALTH", 812.40, 0.28, 0.61, 3_400_000, 772.0),
    Instrument("PFE", "Pfizer Inc.", "NYSE", "HEALTH", 25.62, 0.22, 0.58, 34_000_000, 145.0),
    Instrument("UNH", "UnitedHealth Group", "NYSE", "HEALTH", 542.10, 0.26, 0.63, 3_100_000, 498.0),
    Instrument("COST", "Costco Wholesale", "NASDAQ", "CONSUMER", 918.35, 0.19, 0.79, 2_000_000, 407.0),
    Instrument("NKE", "NIKE Inc. Class B", "NYSE", "CONSUMER", 76.90, 0.29, 0.92, 11_000_000, 114.0),
)

BY_SYMBOL: dict[str, Instrument] = {i.symbol: i for i in _INSTRUMENTS}
ALL_SYMBOLS: tuple[str, ...] = tuple(BY_SYMBOL)


def get(symbol: str) -> Instrument | None:
    return BY_SYMBOL.get(symbol.upper().strip())


def exists(symbol: str) -> bool:
    return symbol.upper().strip() in BY_SYMBOL


def sector_members(sector: str) -> tuple[Instrument, ...]:
    return tuple(i for i in _INSTRUMENTS if i.sector == sector)


def sector_label(sector_code: str) -> str:
    return SECTORS.get(sector_code, sector_code)


def search(query: str, limit: int = 8) -> list[Instrument]:
    """Rank by prefix-on-symbol > substring-on-symbol > substring-on-name."""
    q = query.strip().upper()
    if not q:
        return list(_INSTRUMENTS[:limit])

    scored: list[tuple[int, Instrument]] = []
    for inst in _INSTRUMENTS:
        name = inst.name.upper()
        if inst.symbol == q:
            rank = 0
        elif inst.symbol.startswith(q):
            rank = 1
        elif name.startswith(q):
            rank = 2
        elif q in inst.symbol:
            rank = 3
        elif q in name:
            rank = 4
        elif q in sector_label(inst.sector).upper():
            rank = 5
        else:
            continue
        scored.append((rank, inst))

    scored.sort(key=lambda pair: (pair[0], -pair[1].market_cap_b))
    return [inst for _, inst in scored[:limit]]
