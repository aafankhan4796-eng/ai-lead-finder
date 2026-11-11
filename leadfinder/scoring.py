"""Transparent lead scoring: every point a company gets can be traced to one criterion.

Score = weighted average of six criterion scores (each 0-1), shown as 0-100.
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

REQUIRED = ["company", "sector", "employees"]
OPTIONAL_DEFAULTS = {
    "city": "", "funding_stage": "", "months_since_funding": None, "open_roles": 0,
    "data_maturity": 3, "has_ai_team": "no", "contact_role": "", "website": "", "notes": "",
}
CRITERIA = ["sector", "size", "location", "momentum", "data", "need"]
LABELS = {
    "sector": "Sector fit", "size": "Company size", "location": "Location",
    "momentum": "Growth signals", "data": "Data maturity", "need": "Need for outside help",
}


@dataclass
class Profile:
    """Ideal customer profile (ICP) plus how much each criterion matters."""
    name: str = "Custom"
    sectors: list = field(default_factory=list)          # empty = any sector
    min_employees: int = 20
    max_employees: int = 500
    cities: list = field(default_factory=list)           # empty = anywhere
    prefer_no_ai_team: bool = True
    weights: dict = field(default_factory=lambda: {c: 1.0 for c in CRITERIA})
    pitch: str = "a short, supervised AI proof of concept"


PRESETS = {
    "B2B AI services": Profile(
        name="B2B AI services",
        sectors=["Fintech", "Software", "Logistics", "Healthtech", "Retail & e-commerce", "Energy & climate",
                 "Proptech", "Legaltech"],
        min_employees=20, max_employees=500, cities=[],
        prefer_no_ai_team=True,
        weights={"sector": 1.0, "size": 1.0, "location": 0.5, "momentum": 1.0, "data": 1.5, "need": 1.5},
        pitch="short AI proof-of-concept projects for growing companies",
    ),
    "Small organisations & non-profits": Profile(
        name="Small organisations & non-profits",
        sectors=["Non-profit", "Edtech", "AgriTech", "Energy & climate", "Food & beverage"],
        min_employees=3, max_employees=80, cities=["Amsterdam", "Utrecht", "Rotterdam", "The Hague"],
        prefer_no_ai_team=True,
        weights={"sector": 1.5, "size": 1.5, "location": 1.0, "momentum": 0.5, "data": 0.5, "need": 1.0},
        pitch="practical consulting support for small teams",
    ),
}


def load_companies(df: pd.DataFrame) -> pd.DataFrame:
    """Validate an uploaded table and fill optional columns with neutral defaults."""
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")
    for col, default in OPTIONAL_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
    df["employees"] = pd.to_numeric(df["employees"], errors="coerce")
    df["open_roles"] = pd.to_numeric(df["open_roles"], errors="coerce").fillna(0)
    df["data_maturity"] = pd.to_numeric(df["data_maturity"], errors="coerce").fillna(3).clip(1, 5)
    df["months_since_funding"] = pd.to_numeric(df["months_since_funding"], errors="coerce")
    df = df.dropna(subset=["company", "employees"])
    return df.reset_index(drop=True)


def size_score(employees: float, lo: int, hi: int) -> float:
    """1.0 inside the target band, fading to 0 at half / double the band edges."""
    if lo <= employees <= hi:
        return 1.0
    if employees < lo:
        return max(0.0, (employees - lo / 2) / (lo / 2)) if lo > 0 else 0.0
    return max(0.0, 1 - (employees - hi) / hi)


def momentum_score(months_since_funding: Optional[float], open_roles: float) -> float:
    """Recent funding and active hiring suggest budget, change and openness to new projects."""
    funding = 0.0 if pd.isna(months_since_funding) else max(0.0, 1 - months_since_funding / 24)
    hiring = min(open_roles / 10, 1.0)
    return 0.5 * funding + 0.5 * hiring


def score_row(r: pd.Series, p: Profile) -> dict:
    s = {
        "sector": 1.0 if not p.sectors or r["sector"] in p.sectors else 0.0,
        "size": size_score(r["employees"], p.min_employees, p.max_employees),
        "location": 1.0 if not p.cities or r["city"] in p.cities else 0.3,
        "momentum": momentum_score(r["months_since_funding"], r["open_roles"]),
        "data": (r["data_maturity"] - 1) / 4,
        "need": (1.0 if str(r["has_ai_team"]).strip().lower() in ("no", "false", "0", "") else 0.2)
        if p.prefer_no_ai_team else 0.6,
    }
    total_w = sum(p.weights.get(c, 0) for c in CRITERIA) or 1
    s["score"] = round(100 * sum(s[c] * p.weights.get(c, 0) for c in CRITERIA) / total_w)
    return s


def tier(score: int) -> str:
    return "A" if score >= 75 else "B" if score >= 55 else "C"


def reasons(r: pd.Series, s: dict, p: Profile) -> str:
    """Plain-English 'why this lead' line from the strongest and weakest criteria."""
    good, bad = [], []
    if s["sector"] == 1 and p.sectors:
        good.append(f"target sector ({r['sector']})")
    elif s["sector"] == 0:
        bad.append(f"sector {r['sector']} is outside the profile")
    if s["size"] == 1:
        good.append(f"{int(r['employees'])} employees, in the sweet spot")
    elif s["size"] < 0.5:
        bad.append(f"size ({int(r['employees'])} employees) is off-profile")
    if s["momentum"] >= 0.6:
        good.append("recent funding or active hiring")
    if s["data"] >= 0.75:
        good.append("data-rich")
    elif s["data"] <= 0.25:
        bad.append("little usable data")
    if p.prefer_no_ai_team and s["need"] == 1:
        good.append("no in-house AI team")
    elif p.prefer_no_ai_team:
        bad.append("already has an AI team")
    parts = []
    if good:
        parts.append("Strong: " + ", ".join(good))
    if bad:
        parts.append("Watch: " + ", ".join(bad))
    return ". ".join(parts) + "." if parts else "Average fit on all criteria."


def rank(df: pd.DataFrame, p: Profile) -> pd.DataFrame:
    """Score every company and return them best first, with tier and reasons."""
    scored = df.apply(lambda r: pd.Series(score_row(r, p)), axis=1)
    why = [reasons(df.loc[i], scored.loc[i].to_dict(), p) for i in df.index]
    scored = scored.rename(columns={c: f"s_{c}" for c in CRITERIA})  # avoid clashing with input columns
    out = pd.concat([df, scored], axis=1)
    out["score"] = out["score"].astype(int)
    out["tier"] = out["score"].apply(tier)
    if p.sectors:  # an off-sector company can be a good lead, but never a top-tier one
        out.loc[(out["s_sector"] == 0) & (out["tier"] == "A"), "tier"] = "B"
    out["why"] = why
    return out.sort_values(["score", "company"], ascending=[False, True]).reset_index(drop=True)
