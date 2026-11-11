"""Personalised outreach drafts: template-based by default, optionally rewritten by Claude."""

import os
from typing import Optional

import pandas as pd

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
LINKEDIN_LIMIT = 300  # characters allowed in a LinkedIn connection note

HOOKS = {
    "Manual reporting in spreadsheets": "automating the reporting you now do in spreadsheets",
    "Growing customer support volume": "an AI assistant that handles common customer questions",
    "Large document archive": "making your document archive searchable with AI",
    "Wants to forecast demand": "a demand forecasting prototype",
    "Recently launched a new product": "using AI to learn faster from your new product's users",
    "Expanding to Germany": "a quick AI-assisted market scan for Germany",
    "Lots of customer feedback data": "turning your customer feedback into clear themes with AI",
    "Scheduling and planning done by hand": "automating planning and scheduling",
}


def idea_for(r: pd.Series) -> str:
    """One concrete project idea, based on the notes column when there is one."""
    note = str(r.get("notes") or "").strip()
    if note in HOOKS:
        return HOOKS[note]
    if note:
        return f"an AI prototype around {note[0].lower() + note[1:]}"
    return f"one practical AI use case in {str(r['sector']).lower()}"


def drafts(r: pd.Series, sender: str, org: str, pitch: str) -> dict:
    """Three messages for one lead: LinkedIn note, first email, follow-up."""
    company = r["company"]
    idea = idea_for(r)
    linkedin = (f"Hi, I'm {sender} from {org}. I came across {company} and had an idea: {idea}. "
                f"Open to a 15-min chat?")
    if len(linkedin) > LINKEDIN_LIMIT:
        linkedin = f"Hi, I'm {sender} from {org}. Idea for {company}: {idea}. Open to a 15-min chat?"
    email = "\n".join([
        f"Subject: An AI idea for {company}",
        "",
        "Hi [first name],",
        "",
        f"I'm {sender} from {org}. We run {pitch}.",
        "",
        f"Reading about {company}, one idea stood out: {idea}. "
        "The aim would be a working prototype and a clear view of whether it is worth taking further.",
        "",
        "Would a 15-minute call next week make sense?",
        "",
        "If this isn't relevant, just let me know and I won't follow up.",
        "",
        "Best regards,",
        sender,
        org,
    ])
    follow_up = (f"Hi, a quick follow-up on my note about {idea} for {company}. "
                 "Happy to share an example of a similar project. Would a short call be useful?")
    return {"linkedin": linkedin, "email": email, "follow_up": follow_up}


def ai_rewrite(text: str, r: pd.Series, api_key: Optional[str] = None) -> Optional[str]:
    """Optional: ask Claude to make the email more specific. Returns None without a key or on error."""
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        facts = r[["company", "sector", "city", "employees", "funding_stage", "notes"]].to_dict()
        prompt = ("Rewrite this outreach email to be warmer and more specific, under 130 words. Use ONLY these "
                  f"facts about the company, invent nothing, keep the opt-out line:\n{facts}\n\nEmail:\n{text}")
        msg = client.messages.create(model=DEFAULT_MODEL, max_tokens=400,
                                     messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text.strip()
    except Exception:
        return None
