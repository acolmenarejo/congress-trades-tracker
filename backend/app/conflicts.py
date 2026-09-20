"""Heuristic "possible conflict of interest" detector: flags a trade when the
member sits on a committee whose jurisdiction plausibly covers the traded
company's sector (e.g. Energy and Commerce + MSFT). This is NOT proof of
wrongdoing -- STOCK Act trading is legal for almost all members -- it's a
transparency signal in the same spirit as how outlets like the NYT/Insider
flag committee overlap in their congressional-trading coverage. Keep the
ticker/committee maps conservative (specific, well-known names only) to
avoid false positives on real, named people.

Mirrored in TypeScript at frontend/src/lib/conflictOfInterest.ts -- keep both
in sync if you change the mapping.
"""
from __future__ import annotations

# Deliberately split what used to be one generic "Tecnología" bucket. A
# congressperson on the telecom/internet-platform subcommittee has real
# jurisdiction over Google/Meta (Section 230, ad-market antitrust, video and
# streaming regulation) but NOT over Microsoft or Oracle, whose business is
# enterprise software with no meaningful tie to that subcommittee's actual
# remit -- lumping them together produced flags that didn't hold up (a real
# example: Kean sits on Energy and Commerce - Communications and Technology,
# which genuinely covers GOOGL, but not MSFT).
TICKER_SECTORS: dict[str, list[str]] = {
    "GOOGL": ["Internet y Plataformas", "Inteligencia Artificial"],
    "GOOG": ["Internet y Plataformas", "Inteligencia Artificial"],
    "META": ["Internet y Plataformas", "Inteligencia Artificial"],
    "AMZN": ["Internet y Plataformas", "Inteligencia Artificial"],
    "NFLX": ["Internet y Plataformas"],

    "NVDA": ["Semiconductores y Hardware", "Inteligencia Artificial"],
    "AMD": ["Semiconductores y Hardware"], "INTC": ["Semiconductores y Hardware"],
    "QCOM": ["Semiconductores y Hardware"], "AVGO": ["Semiconductores y Hardware"],
    "TSM": ["Semiconductores y Hardware"], "MU": ["Semiconductores y Hardware"],
    "AAPL": ["Semiconductores y Hardware"],

    "MSFT": ["Inteligencia Artificial"],

    "PANW": ["Ciberseguridad"], "CRWD": ["Ciberseguridad"], "NET": ["Ciberseguridad"],
    "ZS": ["Ciberseguridad"], "FTNT": ["Ciberseguridad"],

    "PLTR": ["Defensa y Aeroespacial", "Ciberseguridad", "Inteligencia Artificial"],
    "LMT": ["Defensa y Aeroespacial"], "RTX": ["Defensa y Aeroespacial"], "NOC": ["Defensa y Aeroespacial"],
    "GD": ["Defensa y Aeroespacial"], "BA": ["Defensa y Aeroespacial"], "LHX": ["Defensa y Aeroespacial"],
    "HII": ["Defensa y Aeroespacial"], "TXT": ["Defensa y Aeroespacial"], "LDOS": ["Defensa y Aeroespacial"],
    "KTOS": ["Defensa y Aeroespacial"],

    "XOM": ["Energía"], "CVX": ["Energía"], "COP": ["Energía"], "OXY": ["Energía"], "SLB": ["Energía"],
    "EOG": ["Energía"], "PSX": ["Energía"], "VLO": ["Energía"], "MPC": ["Energía"], "WMB": ["Energía"],
    "KMI": ["Energía"], "DUK": ["Energía"], "SO": ["Energía"], "NEE": ["Energía"], "EXC": ["Energía"],

    "JPM": ["Servicios Financieros"], "BAC": ["Servicios Financieros"], "WFC": ["Servicios Financieros"],
    "C": ["Servicios Financieros"], "GS": ["Servicios Financieros"], "MS": ["Servicios Financieros"],
    "SCHW": ["Servicios Financieros"], "BLK": ["Servicios Financieros"], "AXP": ["Servicios Financieros"],
    "V": ["Servicios Financieros"], "MA": ["Servicios Financieros"], "PYPL": ["Servicios Financieros"],
    "SQ": ["Servicios Financieros"], "COIN": ["Servicios Financieros"], "USB": ["Servicios Financieros"],
    "PNC": ["Servicios Financieros"], "TFC": ["Servicios Financieros"],

    "PFE": ["Salud y Farmacéutica"], "MRNA": ["Salud y Farmacéutica"], "JNJ": ["Salud y Farmacéutica"],
    "MRK": ["Salud y Farmacéutica"], "ABBV": ["Salud y Farmacéutica"], "LLY": ["Salud y Farmacéutica"],
    "BMY": ["Salud y Farmacéutica"], "UNH": ["Salud y Farmacéutica"], "CVS": ["Salud y Farmacéutica"],
    "GILD": ["Salud y Farmacéutica"], "AMGN": ["Salud y Farmacéutica"], "REGN": ["Salud y Farmacéutica"],
    "VRTX": ["Salud y Farmacéutica"], "ISRG": ["Salud y Farmacéutica"], "ABT": ["Salud y Farmacéutica"],
    "CI": ["Salud y Farmacéutica"], "HUM": ["Salud y Farmacéutica"],

    "T": ["Telecomunicaciones"], "VZ": ["Telecomunicaciones"], "TMUS": ["Telecomunicaciones"],
    "CMCSA": ["Telecomunicaciones"], "CHTR": ["Telecomunicaciones"],

    "ADM": ["Agricultura"], "BG": ["Agricultura"], "DE": ["Agricultura"], "MOS": ["Agricultura"],
    "CF": ["Agricultura"], "CTVA": ["Agricultura"],
}

# Deliberately narrow, mostly at SUBCOMMITTEE level. A rule on a parent
# committee name is only safe when the whole committee's jurisdiction is
# genuinely that specific (Armed Services, Financial Services, Agriculture)
# -- a broad committee like "Energy and Commerce" (which despite its name
# also covers telecom, tech, and health) must NOT get a blanket rule, or
# every member on it gets flagged for every one of those sectors regardless
# of which of its ~6 subcommittees they actually sit on. Broad committees
# like Appropriations, Ways and Means or Oversight are excluded entirely --
# their jurisdiction is too wide to mean anything as a sector signal.
# Sourced from each (sub)committee's own published jurisdiction statement --
# e.g. Energy and Commerce's C&T subcommittee explicitly covers "video,
# streaming, media... Internet and interactive computer service liability
# protection... cybersecurity" (energycommerce.house.gov), which is why it
# maps to platforms + cyber, but NOT to hardware/enterprise-software makers
# who just happen to also be "tech".
COMMITTEE_RULES: list[tuple[str, list[str]]] = [
    ("Energy and Commerce - Communications and Technology", ["Internet y Plataformas", "Telecomunicaciones", "Ciberseguridad"]),
    ("Energy and Commerce - Energy", ["Energía"]),
    ("Energy and Commerce - Health", ["Salud y Farmacéutica"]),
    ("Financial Services", ["Servicios Financieros"]),
    ("Armed Services", ["Defensa y Aeroespacial"]),
    ("Permanent Select Committee on Intelligence", ["Defensa y Aeroespacial", "Ciberseguridad"]),
    ("Agriculture", ["Agricultura"]),
    ("Natural Resources - Energy and Mineral Resources", ["Energía"]),
    ("Science, Space, and Technology", ["Semiconductores y Hardware", "Defensa y Aeroespacial", "Inteligencia Artificial"]),
    ("Artificial Intelligence", ["Inteligencia Artificial"]),
    (
        "Strategic Competition Between the United States and the Chinese Communist Party",
        ["Semiconductores y Hardware", "Defensa y Aeroespacial"],
    ),
    ("Veterans' Affairs - Health", ["Salud y Farmacéutica"]),
    ("Transportation and Infrastructure - Aviation", ["Defensa y Aeroespacial"]),
]


def sectors_for_ticker(ticker: str | None) -> list[str]:
    if not ticker:
        return []
    return TICKER_SECTORS.get(ticker.upper(), [])


class ConflictMatch:
    __slots__ = ("sectors", "committees")

    def __init__(self, sectors: list[str], committees: list[str]):
        self.sectors = sectors
        self.committees = committees


def detect_conflict(ticker: str | None, committees: str | None) -> ConflictMatch | None:
    """Returns the overlapping sectors + the specific (sub)committee name(s)
    that triggered the match, if this looks like a possible conflict of
    interest, else None. Always report the committee alongside the sector so
    the flag is auditable, not a vague "this sector" claim."""
    ticker_sectors = sectors_for_ticker(ticker)
    if not ticker_sectors or not committees:
        return None

    matched = [
        (keyword, sectors) for keyword, sectors in COMMITTEE_RULES
        if keyword in committees and any(s in ticker_sectors for s in sectors)
    ]
    if not matched:
        return None

    sectors = list({s for _, sectors in matched for s in sectors if s in ticker_sectors})
    committee_names = list(dict.fromkeys(keyword for keyword, _ in matched))
    return ConflictMatch(sectors=sectors, committees=committee_names)
