"""Entity normalisation (Member 1). A-G4 implements extract_entities().

PHASE 1: only the shared constant below exists, because the backend imports it as
`from app.ml.entities import FREE_MAIL_DOMAINS` (guidebook B5). List from Section 6.
"""

FREE_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "outlook.com",
        "yahoo.com",
        "hotmail.com",
        "proton.me",
        "rediffmail.com",
    }
)
