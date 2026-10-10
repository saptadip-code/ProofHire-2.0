#!/usr/bin/env python
"""Seeded synthetic listing generator (Member 1 / AI-ML). Guidebook A3. Replaces data cleaning (change C1).

    PYTHONPATH=backend python ml/data/generate_synthetic.py --n 6000 --risky-ratio 0.38 --seed 42 \
        --out ml/data/listings_synthetic.csv

* Fully deterministic for a given (--n, --risky-ratio, --seed). Never edit the CSV by hand.
* Optional fields are written as EMPTY STRINGS on purpose (no cleaning step); features.py handles blanks.
* ALL DATA IS SYNTHETIC: fictional companies, invented salary medians. It is a benchmark, not real-world data.

Generation rules implemented (guidebook A3):
  risky mix  advance_fee 30 / unrealistic_pay 20 / data_harvest 15 / ghost_company 15 / mlm_pyramid 10 / fake_offer_letter 10
  15% of risky rows are 'subtle' (polished text, corporate-looking email, one or two weak signals)
  10% of legit rows are 'messy' (small startups: free-mail contact, no website, short text)
  2% of labels are flipped at random (label noise; mention in the limitations text)
  three paraphrase banks per phrase type, mixed randomly, sentence order shuffled
  legit salary = benchmark median x lognormal(0, 0.35); unrealistic_pay is 3x to 8x
  split: train 70 / val 15 / test 15, stratified by scam_pattern (legit is its own group);
         fake_offer_letter rows are ALL written as split='holdout' (never seen in training).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for _p in (str(HERE), str(REPO_ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lexicons as L  # noqa: E402  (ml/data/lexicons.py)
from app.ml.entities import FREE_MAIL_DOMAINS  # noqa: E402  (shared list, guidebook B5)

# ------------------------------------------------------------------ contract constants
COLUMNS = [
    "listing_id", "title", "company_name", "description", "requirements", "location",
    "work_mode", "employment_type", "salary_min", "salary_max", "pay_period",
    "contact_email", "contact_phone", "application_channel", "company_website",
    "upfront_fee_amount", "interview_mode", "scam_pattern", "difficulty", "label", "split",
]
SCAM_PATTERNS = ["legit", "advance_fee", "data_harvest", "unrealistic_pay", "ghost_company", "mlm_pyramid", "fake_offer_letter"]
RISKY_MIX = [
    ("advance_fee", 0.30), ("unrealistic_pay", 0.20), ("data_harvest", 0.15),
    ("ghost_company", 0.15), ("mlm_pyramid", 0.10), ("fake_offer_letter", 0.10),
]
SUBTLE_SHARE = 0.15
MESSY_SHARE = 0.10
LABEL_NOISE = 0.02
TRAIN_FRACTION, VAL_FRACTION = 0.70, 0.15  # test = remainder
HOLDOUT_PATTERN = "fake_offer_letter"
DEFAULT_N, DEFAULT_RISKY_RATIO, DEFAULT_SEED = 6000, 0.38, 42

# ------------------------------------------------------------------ distributions
EMP_LEGIT = [("internship", 45), ("full_time", 35), ("part_time", 8), ("contract", 12)]
EMP_RISKY = [("internship", 42), ("full_time", 22), ("part_time", 24), ("contract", 12)]
WORK_LEGIT = [("onsite", 50), ("hybrid", 30), ("remote", 20)]
WORK_RISKY = [("remote", 50), ("onsite", 30), ("hybrid", 20)]
CHAN_LEGIT = [("email", 40), ("website_form", 40), ("linkedin_dm", 8), ("phone", 5), ("unknown", 5), ("whatsapp", 1), ("telegram", 1)]
CHAN_RISKY = [("whatsapp", 38), ("telegram", 25), ("email", 15), ("phone", 10), ("unknown", 7), ("website_form", 3), ("linkedin_dm", 2)]
INT_LEGIT = [("video_call", 40), ("in_person", 25), ("phone_call", 25), ("chat_only", 3), ("none", 7)]
INT_RISKY = [("none", 40), ("chat_only", 35), ("phone_call", 10), ("video_call", 10), ("in_person", 5)]
INT_FAKE_OFFER = [("none", 50), ("chat_only", 35), ("phone_call", 10), ("video_call", 5)]
FREE_MAIL_WEIGHTS = {"gmail.com": 6, "yahoo.com": 2, "outlook.com": 2, "hotmail.com": 1, "proton.me": 0.5, "rediffmail.com": 1}
WEAK_SIGNALS = ["chat_only", "messaging", "no_website", "free_email", "lookalike_email", "pay_high", "vague_req", "mild_urgency", "no_interview"]


# ------------------------------------------------------------------ helpers
def _pick(rng: random.Random, pairs):
    return rng.choices([p[0] for p in pairs], [p[1] for p in pairs])[0]


def _allocate(total: int, weights: list[float]) -> list[int]:
    """Largest-remainder allocation: sums exactly to total."""
    raw = [total * w for w in weights]
    out = [int(x) for x in raw]
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - out[i], -i), reverse=True)
    for i in order[: total - sum(out)]:
        out[i] += 1
    return out


def _round_money(v: float) -> int:
    step = 500 if v >= 10000 else 100
    return max(int(round(v / step) * step), 1000)


def _words(s: str) -> int:
    return len(s.split())


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown (not a git checkout when generated)"


def _free_mail_domain(rng: random.Random) -> str:
    domains = sorted(d for d in FREE_MAIL_DOMAINS if d in FREE_MAIL_WEIGHTS) or sorted(FREE_MAIL_DOMAINS)
    return rng.choices(domains, [FREE_MAIL_WEIGHTS.get(d, 1) for d in domains])[0]


def _sentence(rng: random.Random, ptype: str, ctx: dict) -> str:
    bank = rng.choice(L.PHRASE_BANKS[ptype])  # one of three paraphrase banks
    return rng.choice(bank).format(**ctx)


def _assemble(rng, ctx, required, fillers, lo, hi, intro_first=True):
    """Pick one sentence per required type, add unique filler sentences until >= target words, shuffle order."""
    target = rng.randint(lo, hi)
    parts: list[str] = []
    seen: set[str] = set()
    intro = None
    for t in required:
        s = _sentence(rng, t, ctx)
        if s in seen:
            continue
        seen.add(s)
        if intro_first and t in ("intro", "intro_vague") and intro is None:
            intro = s
        else:
            parts.append(s)
    pool = []
    for t in fillers:
        for bank in L.PHRASE_BANKS[t]:
            pool.extend(bank)
    pool = [p.format(**ctx) for p in pool]
    rng.shuffle(pool)
    cur = _words(" ".join(parts + ([intro] if intro else [])))
    for s in pool:
        if cur >= target and cur >= lo:
            break
        if s in seen or cur + _words(s) > hi:
            continue
        seen.add(s)
        parts.append(s)
        cur += _words(s)
    rng.shuffle(parts)
    if intro:
        parts.insert(0, intro)
    text = " ".join(parts)
    # Hard guarantee for the A3 column contract (50-250 words).
    guard = 0
    while _words(text) < lo and guard < 20:
        extra = rng.choice(pool) if pool else _sentence(rng, "generic_filler", ctx)
        if extra not in seen:
            seen.add(extra)
            text += " " + extra
        guard += 1
    return text


def _requirements(rng, ctx, bank: str, n_sent, max_words=80) -> str:
    sents = rng.choice(L.PHRASE_BANKS[bank])
    sents = [s.format(**ctx) for s in sents]
    rng.shuffle(sents)
    out: list[str] = []
    for s in sents[:n_sent]:
        if _words(" ".join(out + [s])) <= max_words:
            out.append(s)
    return " ".join(out)


def _fee_amount(rng: random.Random) -> int:
    if rng.random() < 0.7:
        return rng.choice([499, 599, 749, 999, 1199, 1499, 1999, 2499, 2999, 3499, 4999, 5999, 7499, 9999])
    return rng.randint(499, 9999)


# ------------------------------------------------------------------ one listing
def build_listing(rng: random.Random, pattern: str, difficulty: str) -> dict:
    risky = pattern != "legit"
    subtle = difficulty == "subtle"
    messy = difficulty == "messy"
    strong = risky and not subtle  # rows with the full pattern signature

    role = rng.choice(L.ROLES)
    emp = _pick(rng, EMP_RISKY if strong else EMP_LEGIT)
    work_mode = _pick(rng, WORK_RISKY if strong else WORK_LEGIT)
    ghost = strong and pattern == "ghost_company"

    # ---- company / slug
    prefix = rng.choice(L.COMPANY_PREFIXES)
    suffix = rng.choice(L.GHOST_SUFFIXES if ghost else L.COMPANY_SUFFIXES)
    company = f"{prefix} {suffix}"
    slug = prefix.lower()
    tld = rng.choices([".com", ".in", ".io", ".co.in"], [70, 15, 8, 7])[0]

    # ---- weak signals for subtle rows
    weak = set(rng.sample(WEAK_SIGNALS, rng.choice([1, 2]))) if subtle else set()

    # ---- contact channel / interview
    if strong:
        channel = _pick(rng, CHAN_RISKY)
        interview = _pick(rng, INT_FAKE_OFFER if pattern == HOLDOUT_PATTERN else INT_RISKY)
    else:
        channel = _pick(rng, CHAN_LEGIT)
        interview = _pick(rng, INT_LEGIT)
    if "messaging" in weak:
        channel = rng.choice(["whatsapp", "telegram"])
    if "chat_only" in weak:
        interview = "chat_only"
    if "no_interview" in weak:
        interview = "none"

    # ---- email kind and website
    if messy or "free_email" in weak:
        email_kind = "free"
    elif "lookalike_email" in weak:
        email_kind = "lookalike"
    elif strong:
        email_kind = _pick(rng, [("free", 70), ("lookalike", 15), ("mismatch", 15)] if ghost
                           else [("free", 50), ("lookalike", 25), ("mismatch", 25)])
    else:
        email_kind = "corp"

    if messy:
        site_missing = rng.random() < 0.9
    elif strong:
        site_missing = rng.random() < (0.9 if ghost else 0.5)
    else:
        site_missing = rng.random() < 0.05
    if "no_website" in weak:
        site_missing = True
    website = "" if site_missing else f"https://{slug}{tld}"

    if email_kind == "corp":
        email = f"{rng.choice(['careers', 'hr', 'recruitment', 'jobs', 'talent', 'hiring'])}@{slug}{tld}"
    elif email_kind == "lookalike":
        email = f"careers@{slug}-jobs.in"
    elif email_kind == "mismatch":
        other = rng.choice([p for p in L.COMPANY_PREFIXES if p != prefix]).lower()
        email = f"hr@{other}.com"
    else:
        local = f"{slug}.{rng.choice(['hr', 'jobs', 'careers', 'recruiter', 'hiring'])}"
        if rng.random() < 0.4:
            local += str(rng.randint(1, 99))
        email = f"{local}@{_free_mail_domain(rng)}"
    if not risky and channel == "website_form" and rng.random() < 0.4:
        email = ""  # applications via the website form only

    phone_p = 0.85 if strong else (0.8 if messy else 0.45)
    phone = ""
    if rng.random() < phone_p:
        phone = f"{rng.choice('6789')}{rng.randint(0, 999999999):09d}"
        if rng.random() < 0.3:
            phone = "+91 " + phone

    # ---- fee plan
    fee, fee_type = 0, None
    if strong:
        if pattern == "advance_fee":
            fee, fee_type = _fee_amount(rng), ("fee" if rng.random() < 0.9 else None)
        elif pattern == "unrealistic_pay" and rng.random() < 0.10:
            fee, fee_type = _fee_amount(rng), "fee"
        elif pattern == "mlm_pyramid" and rng.random() < 0.55:
            fee, fee_type = rng.choice([999, 1499, 1999, 2499, 2999, 4999]), "mlm_kit"
        elif pattern == "fake_offer_letter" and rng.random() < 0.7:
            fee, fee_type = rng.choice([1000, 1250, 1500, 2000, 2500, 3500, 4500, 6500]), "offer_letter_fee"

    # ---- salary
    median = role["monthly_median_inr"][emp]
    mult = rng.lognormvariate(0, 0.35)
    stated_p = 0.94
    if messy:
        stated_p = 0.7
    if strong:
        stated_p = 1.0 if pattern in ("unrealistic_pay", "advance_fee", "data_harvest", "fake_offer_letter") else 0.85
        if pattern == "unrealistic_pay":
            mult = rng.uniform(3.0, 8.0)
        elif pattern == "advance_fee":
            mult *= rng.choice([1.0, 1.3, 1.6])
        elif pattern == "data_harvest":
            mult *= rng.uniform(1.0, 2.0)
        elif pattern == "mlm_pyramid" and rng.random() < 0.5:
            mult = rng.uniform(2.0, 4.0)
        elif pattern in ("fake_offer_letter", "ghost_company"):
            mult *= 1.2 if pattern == "fake_offer_letter" else 1.1
    if "pay_high" in weak:
        mult = rng.uniform(1.8, 2.6)
    stated = rng.random() < stated_p
    if not strong and emp == "internship" and not messy and rng.random() < 0.06:
        stated = False  # unpaid internship
    period = "year" if rng.random() < 0.05 else "month"
    monthly_max = _round_money(median * mult)
    smax = smin = 0
    stipend_txt = f"{monthly_max:,}"
    if stated:
        monthly_min = monthly_max if rng.random() < (0.7 if pattern == "unrealistic_pay" and strong else 0.35) \
            else min(monthly_max, _round_money(monthly_max * rng.uniform(0.6, 0.95)))
        factor = 12 if period == "year" else 1
        smax, smin = monthly_max * factor, monthly_min * factor

    # ---- text signals (strong rows) -- decided before writing
    sig = {"hype": False, "no_exp": False, "urgency": False, "wfh": False, "msg": False, "guar": False, "personal": False}
    if strong:
        p = {
            "advance_fee": dict(hype=.5, no_exp=.5, urgency=.55, wfh=.4, msg=.5, guar=.2),
            "unrealistic_pay": dict(hype=1.0, no_exp=.8, urgency=.5, wfh=.5, msg=.4, guar=.1),
            "data_harvest": dict(hype=.3, no_exp=.2, urgency=.3, wfh=.4, msg=.5, guar=.2, personal=1.0),
            "ghost_company": dict(msg=.6),
            "mlm_pyramid": dict(hype=.5, no_exp=.5, urgency=.3, wfh=.3, msg=.3, guar=.1),
            "fake_offer_letter": dict(urgency=.2, msg=.4, guar=.5),
        }[pattern]
        for k, v in p.items():
            sig[k] = rng.random() < v
        if sig["hype"] and not stated:
            stated = True
            factor = 12 if period == "year" else 1
            smax = monthly_max * factor
            smin = monthly_max * factor
    elif "mild_urgency" in weak:
        sig["urgency"] = True

    # ---- title
    base_title = rng.choice(role["intern_titles"] if emp == "internship" else role["job_titles"])
    title = base_title
    if strong:
        hype_p = {"unrealistic_pay": .8, "advance_fee": .4, "mlm_pyramid": .5, "data_harvest": .3,
                  "fake_offer_letter": .25, "ghost_company": .2}[pattern]
        if rng.random() < hype_p:
            if stated and rng.random() < 0.6:
                title += rng.choice(L.HYPE_TITLE_SUFFIXES_WITH_PAY).format(stipend=stipend_txt.replace(",", ""))
            else:
                title += rng.choice(L.HYPE_TITLE_SUFFIXES)
            if rng.random() < 0.3:
                title = title.upper()

    where_phrase = "remotely" if work_mode == "remote" else f"in {rng.choice(L.CITIES)}"
    skills = rng.sample(role["skills"] * 2 if len(role["skills"]) < 3 else role["skills"], 3)
    ctx = {
        "company": company, "role": base_title, "role_lc": role["role"], "skill1": skills[0], "skill2": skills[1],
        "skill3": skills[2], "where_phrase": where_phrase, "stipend": stipend_txt, "fee": f"{fee:,}" if fee else "0",
        "domain": rng.choice(L.DOMAINS),
    }

    # ---- description
    if not strong:  # legit easy / legit messy / subtle risky share the polished legit structure
        required = ["intro", "responsibilities", "process_legit", "apply_legit"]
        fillers = ["company_blurb", "learning", "culture", "benefits_legit", "responsibilities", "learning"]
        if rng.random() < 0.12 and not risky:
            required.append("no_fee_note")
        if subtle:
            required.append("subtle_" + pattern)
            required.append("company_blurb")
        if sig["urgency"]:
            required.append("mild_urgency")
        lo, hi = (50, 70) if messy else (70, 220)
        if messy:
            fillers = ["responsibilities", "culture", "learning"]
            required = ["intro", "responsibilities", "apply_legit"]
    else:
        req_map = {
            "advance_fee": ["intro", "hype_pay"] if sig["hype"] else ["intro"],
            "unrealistic_pay": ["intro", "hype_pay"],
            "data_harvest": ["intro", "personal_data"],
            "ghost_company": ["intro_vague", "vague"],
            "mlm_pyramid": ["intro", "mlm"],
            "fake_offer_letter": ["intro", "offer_letter"],
        }
        required = list(req_map[pattern])
        if fee_type:
            required.append(fee_type)
        for flag, ptype in (("no_exp", "no_experience"), ("urgency", "urgency"), ("wfh", "wfh"),
                            ("msg", "contact_msg"), ("guar", "guaranteed")):
            if sig[flag]:
                required.append(ptype)
        if sig["hype"] and pattern in ("mlm_pyramid", "data_harvest"):
            required.append("hype_pay")
        if rng.random() < 0.5 and pattern != "ghost_company":
            required.append("responsibilities")
        fillers = ["generic_filler", "generic_filler", "wfh", "culture"] if not ghost else ["generic_filler", "generic_filler"]
        lo, hi = (50, 90) if ghost else (50, 200)
    description = _assemble(rng, ctx, required, fillers, lo, hi)

    # ---- requirements
    if messy:
        requirements = _requirements(rng, ctx, "req_legit", 2, 25) if rng.random() < 0.85 else ""
    elif not strong:
        requirements = _requirements(rng, ctx, "req_legit", rng.randint(4, 5)) if rng.random() < 0.96 else ""
        if "vague_req" in weak:
            requirements = "" if rng.random() < 0.5 else "Basic knowledge of computers."
    else:
        empty_p = 0.5 if ghost else 0.2
        requirements = "" if rng.random() < empty_p else _requirements(rng, ctx, "req_risky", rng.randint(1, 3))

    # ---- location
    if work_mode == "remote" and rng.random() < 0.7:
        location = "Remote"
    elif rng.random() < 0.03:
        location = ""
    else:
        location = rng.choice(L.CITIES)

    return {
        "title": title, "company_name": company, "description": description, "requirements": requirements,
        "location": location, "work_mode": work_mode, "employment_type": emp, "salary_min": smin, "salary_max": smax,
        "pay_period": period, "contact_email": email, "contact_phone": phone, "application_channel": channel,
        "company_website": website, "upfront_fee_amount": fee, "interview_mode": interview,
        "scam_pattern": pattern, "difficulty": difficulty,
    }


# ------------------------------------------------------------------ dataset
def generate_rows(n: int = DEFAULT_N, risky_ratio: float = DEFAULT_RISKY_RATIO, seed: int = DEFAULT_SEED) -> list[dict]:
    rng = random.Random(seed)
    n_risky = round(n * risky_ratio)
    n_legit = n - n_risky
    counts = _allocate(n_risky, [w for _, w in RISKY_MIX])
    risky_plan = [pat for (pat, _), c in zip(RISKY_MIX, counts) for _ in range(c)]
    rng.shuffle(risky_plan)
    n_subtle = round(SUBTLE_SHARE * n_risky)
    plan = [(pat, "subtle" if i < n_subtle else "easy") for i, pat in enumerate(risky_plan)]
    n_messy = round(MESSY_SHARE * n_legit)
    plan += [("legit", "messy" if i < n_messy else "easy") for i in range(n_legit)]
    rng.shuffle(plan)

    rows: list[dict] = []
    seen: set[tuple] = set()
    for i, (pattern, difficulty) in enumerate(plan, 1):
        for _ in range(50):
            row = build_listing(rng, pattern, difficulty)
            key = (row["company_name"], row["title"], row["description"])
            if key not in seen:  # no identical listing anywhere -> no exact-duplicate leakage across splits
                seen.add(key)
                break
        else:
            raise RuntimeError("could not generate a unique listing; vocabulary too small for --n")
        row["listing_id"] = f"SYN-{i:06d}"
        row["label"] = 0 if pattern == "legit" else 1
        rows.append(row)

    # ---- split BEFORE label noise, stratified by scam_pattern (legit is its own group)
    by_group: dict[str, list[int]] = {}
    for idx, r in enumerate(rows):
        by_group.setdefault(r["scam_pattern"], []).append(idx)
    for pattern in sorted(by_group):
        idxs = by_group[pattern]
        if pattern == HOLDOUT_PATTERN:
            for j in idxs:
                rows[j]["split"] = "holdout"
            continue
        rng.shuffle(idxs)
        n_train = round(TRAIN_FRACTION * len(idxs))
        n_val = round(VAL_FRACTION * len(idxs))
        for k, j in enumerate(idxs):
            rows[j]["split"] = "train" if k < n_train else ("val" if k < n_train + n_val else "test")

    # ---- label noise: flip exactly round(2% * n) labels at random
    for j in rng.sample(range(n), round(LABEL_NOISE * n)):
        rows[j]["label"] = 1 - rows[j]["label"]
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in COLUMNS})


def csv_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    noise = sum(1 for r in rows if (r["label"] == 1) != (r["scam_pattern"] != "legit"))
    return {
        "rows": n,
        "label_1_risky": sum(r["label"] for r in rows),
        "label_0_legit": n - sum(r["label"] for r in rows),
        "risky_share": round(sum(r["label"] for r in rows) / n, 4),
        "label_noise_rows": noise,
        "by_split": dict(sorted(Counter(r["split"] for r in rows).items())),
        "by_split_and_label": {f"{s}/{l}": c for (s, l), c in sorted(Counter((r["split"], r["label"]) for r in rows).items())},
        "by_scam_pattern": dict(sorted(Counter(r["scam_pattern"] for r in rows).items())),
        "by_difficulty": dict(sorted(Counter(r["difficulty"] for r in rows).items())),
    }


def write_readme(path: Path, args, rows: list[dict], csv_path: Path) -> None:
    s = summarize(rows)
    lines = [
        "# ProofHire synthetic dataset (`listings_synthetic.csv`)",
        "",
        "**SYNTHETIC BENCHMARK DATA.** Every row is machine-generated from phrase banks with fictional company names and",
        "invented salary medians. It is not real listing data and not verified salary data. Metrics measured on it are a",
        "*synthetic benchmark*, never real-world accuracy.",
        "",
        "## Provenance",
        f"- Command: `PYTHONPATH=backend python ml/data/generate_synthetic.py --n {args.n} --risky-ratio {args.risky_ratio} --seed {args.seed} --out ml/data/listings_synthetic.csv`",
        f"- Seed: **{args.seed}**",
        f"- Generator commit hash (at generation time): `{_git_commit()}`",
        f"- CSV sha256: `{csv_sha256(csv_path)}`",
        "- Never edit the CSV by hand; change the generator and re-run.",
        "",
        "## Counts (actual, from this file)",
        f"- Rows: {s['rows']}; label=1 (risky): {s['label_1_risky']} ({s['risky_share']:.2%}); label=0 (legit): {s['label_0_legit']}",
        f"- Label-noise rows (label disagrees with scam_pattern): {s['label_noise_rows']}",
        f"- Splits: {s['by_split']}",
        f"- scam_pattern: {s['by_scam_pattern']}",
        f"- difficulty: {s['by_difficulty']}",
        "",
        "## Rules",
        "- Risky mix 30/20/15/15/10/10 (advance_fee, unrealistic_pay, data_harvest, ghost_company, mlm_pyramid, fake_offer_letter).",
        "- 15% of risky rows are `subtle`; 10% of legit rows are `messy`.",
        "- 2% of labels are flipped at random (label noise). Flipped rows keep their original scam_pattern.",
        "- Split: train 70 / val 15 / test 15, stratified by scam_pattern; all `fake_offer_letter` rows are `holdout` (never in train/val/test).",
        "- Optional fields are empty strings on purpose; salary is 0 when not stated.",
        "",
        "## Known limitations",
        "- Generator and evidence rules share vocabulary, so synthetic scores will look high; use the pattern-holdout and the hand-written set for harder checks.",
        "- Company names and phrase banks repeat across splits (small fictional vocabulary); only exact duplicate listings are prevented.",
        "- Messy legit rows still have descriptions of at least 50 words (A3 column contract), so `vague_desc` is rarely/never set in this data.",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the ProofHire synthetic listings CSV (seeded).")
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--risky-ratio", type=float, default=DEFAULT_RISKY_RATIO)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=str(HERE / "listings_synthetic.csv"))
    ap.add_argument("--readme", default=None, help="README path (default: README.md next to --out)")
    ap.add_argument("--no-readme", action="store_true")
    args = ap.parse_args(argv)

    rows = generate_rows(args.n, args.risky_ratio, args.seed)
    out = Path(args.out)
    write_csv(rows, out)
    if not args.no_readme:
        write_readme(Path(args.readme) if args.readme else out.parent / "README.md", args, rows, out)
    print(summarize(rows))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
