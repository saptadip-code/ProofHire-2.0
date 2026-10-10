"""Lexicons for the ProofHire synthetic data generator (Member 1 / AI-ML). Guidebook A1, A3, A4.

EVERYTHING IN THIS FILE IS SYNTHETIC / FICTIONAL:
  * company names are invented (no real companies),
  * salary medians are invented development numbers for a synthetic benchmark. They are NOT
    verified real-world salary data and must never be presented as such.

This module is also the single source of truth for the two runtime JSON files that inference
reads (guidebook A1):
    backend/app/data/role_benchmarks.json
    backend/app/data/lexicons_runtime.json
Regenerate them with:   python ml/data/lexicons.py --export-runtime
(ml/tests/test_features.py fails if the JSON files drift from this module.)

Offline only. Not imported by the deployed runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SYNTHETIC_NOTICE = (
    "SYNTHETIC DEVELOPMENT DATA. Fictional companies and invented salary medians; "
    "not verified real-world salary or employer data."
)

# --------------------------------------------------------------------- companies
# Invented words only. Combined as "<prefix> <suffix>"; the generator lower-cases the prefix as the domain slug.
COMPANY_PREFIXES = [
    "Nexora", "Brightpath", "Zenvio", "Quantora", "Veltrix", "Orbitek", "Lumivo", "Kriyon",
    "Trivanta", "Altrion", "Pixelor", "Soniq", "Vantro", "Meridex", "Cobaltix", "Auralis",
    "Zephyra", "Novaris", "Quillon", "Datavane", "Cloudreon", "Finlytic", "Greenloop",
    "Hexabyte", "Ionwave", "Kelvora", "Lattixa", "Mobiyo", "Nimbora", "Oakvane", "Qubitra",
    "Radiqo", "Solvanta", "Tarnix", "Umbrion", "Vexora", "Wavelio", "Zentora", "Arvenix",
    "Bluforge", "Cirrusly", "Dynabee", "Emberly", "Fluxora", "Gridlane", "Harbora",
    "Helionix", "Juniq", "Keystra", "Loomix", "Mintora", "Nodelane", "Opalix", "Plexora",
    "Quarkly", "Rivetta", "Stackora", "Tidelane", "Uplinq", "Vividra", "Woventa", "Zypher",
]
COMPANY_SUFFIXES = [
    "Labs", "Technologies", "Solutions", "Systems", "Analytics", "Works", "Digital",
    "Softworks", "Innovations", "Networks", "Consulting", "Infotech", "Dynamics", "Studio",
]
# Used by ghost_company rows: generic, placement-agency style names.
GHOST_SUFFIXES = ["Careers", "Recruiters", "Global Services", "Enterprises", "Hiring Hub", "Job Desk", "Staffing"]

CITIES = ["Bengaluru", "Hyderabad", "Pune", "Chennai", "Delhi NCR", "Mumbai"]
LOCATIONS = CITIES + ["Remote"]  # guidebook A3 location values

DOMAINS = [
    "analytics", "logistics", "healthcare software", "education technology", "fintech",
    "e-commerce", "cloud tooling", "retail software", "agri-tech",
]

# ------------------------------------------------------------------------ roles
# monthly_median_inr values are INVENTED synthetic benchmarks (INR per month).
# 'keywords' drive runtime role detection from the title (longest keyword wins).
ROLES = [
    {"role": "data entry", "keywords": ["data entry"],
     "intern_titles": ["Data Entry Intern", "Data Entry Trainee"],
     "job_titles": ["Data Entry Operator", "Data Entry Executive"],
     "skills": ["typing accuracy", "MS Excel", "attention to detail"],
     "monthly_median_inr": {"internship": 8000, "full_time": 20000, "part_time": 9000, "contract": 16000}},
    {"role": "content writing", "keywords": ["content writ", "copywrit"],
     "intern_titles": ["Content Writing Intern", "Copywriting Intern"],
     "job_titles": ["Content Writer", "Copywriter"],
     "skills": ["clear writing", "research", "SEO basics"],
     "monthly_median_inr": {"internship": 10000, "full_time": 28000, "part_time": 10000, "contract": 22000}},
    {"role": "software engineering", "keywords": ["software developer", "software engineer", "backend developer", "python developer"],
     "intern_titles": ["Software Developer Intern", "Python Developer Intern", "Backend Developer Intern"],
     "job_titles": ["Software Engineer", "Python Developer", "Backend Developer"],
     "skills": ["Python", "data structures", "Git", "REST APIs"],
     "monthly_median_inr": {"internship": 25000, "full_time": 80000, "part_time": 20000, "contract": 65000}},
    {"role": "web development", "keywords": ["web developer", "frontend developer", "web development"],
     "intern_titles": ["Web Developer Intern", "Frontend Developer Intern"],
     "job_titles": ["Web Developer", "Frontend Developer"],
     "skills": ["HTML", "CSS", "JavaScript", "React"],
     "monthly_median_inr": {"internship": 18000, "full_time": 55000, "part_time": 15000, "contract": 45000}},
    {"role": "mobile development", "keywords": ["android developer", "mobile developer", "app developer"],
     "intern_titles": ["Android Developer Intern", "Mobile Developer Intern"],
     "job_titles": ["Android Developer", "Mobile Developer"],
     "skills": ["Kotlin", "Java", "mobile UI basics", "Git"],
     "monthly_median_inr": {"internship": 20000, "full_time": 65000, "part_time": 16000, "contract": 55000}},
    {"role": "data analysis", "keywords": ["data analyst", "data analytics"],
     "intern_titles": ["Data Analyst Intern", "Data Analytics Intern"],
     "job_titles": ["Data Analyst", "Junior Data Analyst"],
     "skills": ["SQL", "Excel", "statistics", "dashboards"],
     "monthly_median_inr": {"internship": 20000, "full_time": 60000, "part_time": 16000, "contract": 50000}},
    {"role": "machine learning", "keywords": ["machine learning", "ml engineer", "data scientist", "data science"],
     "intern_titles": ["Machine Learning Intern", "Data Science Intern"],
     "job_titles": ["Machine Learning Engineer", "Data Scientist"],
     "skills": ["Python", "scikit-learn", "statistics", "model evaluation"],
     "monthly_median_inr": {"internship": 25000, "full_time": 90000, "part_time": 20000, "contract": 75000}},
    {"role": "digital marketing", "keywords": ["digital marketing", "social media", "seo"],
     "intern_titles": ["Digital Marketing Intern", "Social Media Intern"],
     "job_titles": ["Digital Marketing Executive", "Social Media Executive", "SEO Executive"],
     "skills": ["social media tools", "analytics dashboards", "copy editing"],
     "monthly_median_inr": {"internship": 12000, "full_time": 35000, "part_time": 11000, "contract": 28000}},
    {"role": "graphic design", "keywords": ["graphic design", "ui designer", "ux designer"],
     "intern_titles": ["Graphic Design Intern", "UI Designer Intern"],
     "job_titles": ["Graphic Designer", "UX Designer"],
     "skills": ["Figma", "typography", "layout design"],
     "monthly_median_inr": {"internship": 12000, "full_time": 38000, "part_time": 11000, "contract": 32000}},
    {"role": "customer support", "keywords": ["customer support", "customer service", "support executive"],
     "intern_titles": ["Customer Support Intern", "Customer Service Trainee"],
     "job_titles": ["Customer Support Executive", "Customer Service Associate"],
     "skills": ["written communication", "ticketing tools", "patience with customers"],
     "monthly_median_inr": {"internship": 9000, "full_time": 24000, "part_time": 9000, "contract": 20000}},
    {"role": "human resources", "keywords": ["hr executive", "hr intern", "human resources", "recruiter", "talent acquisition"],
     "intern_titles": ["HR Intern", "Human Resources Intern"],
     "job_titles": ["HR Executive", "Talent Acquisition Associate"],
     "skills": ["interview coordination", "spreadsheets", "communication"],
     "monthly_median_inr": {"internship": 10000, "full_time": 30000, "part_time": 10000, "contract": 26000}},
    {"role": "sales", "keywords": ["sales executive", "business development", "sales"],
     "intern_titles": ["Sales Intern", "Business Development Intern"],
     "job_titles": ["Sales Executive", "Business Development Executive"],
     "skills": ["CRM tools", "negotiation basics", "communication"],
     "monthly_median_inr": {"internship": 10000, "full_time": 30000, "part_time": 10000, "contract": 25000}},
    {"role": "business analysis", "keywords": ["business analyst"],
     "intern_titles": ["Business Analyst Intern"],
     "job_titles": ["Business Analyst", "Junior Business Analyst"],
     "skills": ["requirement gathering", "Excel", "process mapping"],
     "monthly_median_inr": {"internship": 18000, "full_time": 60000, "part_time": 15000, "contract": 50000}},
    {"role": "quality assurance", "keywords": ["qa engineer", "qa intern", "quality analyst", "software tester"],
     "intern_titles": ["QA Intern", "Software Tester Intern"],
     "job_titles": ["QA Engineer", "Quality Analyst"],
     "skills": ["test case design", "bug tracking", "attention to detail"],
     "monthly_median_inr": {"internship": 15000, "full_time": 45000, "part_time": 13000, "contract": 38000}},
    {"role": "accounts and finance", "keywords": ["accountant", "accounts executive", "accounts intern", "finance"],
     "intern_titles": ["Finance Intern", "Accounts Intern"],
     "job_titles": ["Accountant", "Accounts Executive"],
     "skills": ["Excel", "bookkeeping basics", "attention to detail"],
     "monthly_median_inr": {"internship": 10000, "full_time": 30000, "part_time": 10000, "contract": 25000}},
    {"role": "operations", "keywords": ["operations executive", "operations"],
     "intern_titles": ["Operations Intern", "Operations Trainee"],
     "job_titles": ["Operations Executive", "Operations Associate"],
     "skills": ["spreadsheets", "coordination", "process documentation"],
     "monthly_median_inr": {"internship": 10000, "full_time": 32000, "part_time": 10000, "contract": 26000}},
]
DEFAULT_BENCHMARK = {"internship": 12000, "full_time": 35000, "part_time": 11000, "contract": 28000}

# -------------------------------------------------- runtime regex / keyword lists (A4, A7)
# Case-insensitive. Shared by features.py (inference) and the generator (so the dataset and the
# evidence rules share vocabulary - the guidebook warns synthetic metrics will therefore look high).
URGENCY_PHRASES = [
    "apply now", "limited seats", "last date today", "hurry", "immediate joining", "urgent hiring",
    "only few seats", "seats filling fast", "today only", "apply immediately", "offer ends", "don't miss",
]
FEE_PATTERNS = [
    r"\b(?:registration|enrol+ment|processing|joining|application|security|training|verification|documentation"
    r"|onboarding|admission|interview|courier|certificate|stamp\s+paper)\s+(?:fee|fees|charge|charges|deposit|amount)\b",
    r"\bsecurity\s+deposit\b",
    r"\b(?:kit|uniform|id\s*card|laptop|software)\s+charges?\b",
    r"\b(?:joining|starter|welcome)\s+kit\b",
    r"\brefundable\b",
    r"\bpay\s+(?:rs\.?|inr|\u20b9)\s*[\d,]+",
    r"\bdeposit\s+(?:of\s+)?(?:rs\.?|inr|\u20b9)\s*[\d,]+",
]
PERSONAL_DATA_PATTERNS = [
    r"\baadhaa?r\b", r"\bpan\s*card\b", r"\bbank\s+account\b", r"\botp\b", r"\bpassport\b", r"\bcvv\b",
    r"\bphoto\s+(?:of\s+)?(?:your\s+)?id\b",
]
GUARANTEED_CLAIM_PATTERNS = [
    r"\bguarantee[d]?\s+(?:job|placement|offer|selection)\b",
    r"\b100\s*%\s*(?:job\s+)?(?:placement|guarantee|selection)\b",
    r"\bassured\s+(?:selection|placement|job|offer)\b",
]
NO_EXPERIENCE_PATTERNS = [
    r"\bno\s+(?:prior\s+)?experience\s+(?:is\s+)?(?:needed|required|necessary)\b",
    r"\bwithout\s+any\s+experience\b",
]
# A match is ignored when one of these words appears shortly before it ("no registration fee").
NEGATION_PATTERN = r"(?:\bno\b|\bnot\b|\bnever\b|\bwithout\b|\bzero\b|\bfree\s+of\b|n't)\s*(?:\w+\s+){0,4}$"

RUNTIME_LEXICONS = {
    "_meta": {"data_type": "development-lexicon", "source": "ml/data/lexicons.py", "notice": SYNTHETIC_NOTICE},
    "urgency_phrases": URGENCY_PHRASES,
    "fee_patterns": FEE_PATTERNS,
    "personal_data_patterns": PERSONAL_DATA_PATTERNS,
    "guaranteed_claim_patterns": GUARANTEED_CLAIM_PATTERNS,
    "no_experience_patterns": NO_EXPERIENCE_PATTERNS,
    "negation_pattern": NEGATION_PATTERN,
}


def role_benchmarks_payload() -> dict:
    return {
        "_meta": {
            "data_type": "synthetic",
            "currency": "INR",
            "unit": "monthly_median",
            "notice": SYNTHETIC_NOTICE,
        },
        "default": dict(DEFAULT_BENCHMARK),
        "roles": [
            {"role": r["role"], "keywords": list(r["keywords"]), "monthly_median_inr": dict(r["monthly_median_inr"])}
            for r in ROLES
        ],
    }


# --------------------------------------------------------------- phrase banks (A3)
# PHRASE_BANKS[type] = THREE paraphrase banks (guidebook A3), each a list of sentence templates.
# The generator picks a random bank, then a random sentence; sentence order is shuffled.
# Placeholders: {company} {role} {role_lc} {skill1} {skill2} {skill3} {where_phrase} {stipend} {fee} {domain}
PHRASE_BANKS = {
    # ---- legitimate-style text
    "intro": [
        ["{company} is hiring a {role} to join our team {where_phrase}.",
         "We are looking for a motivated {role} at {company}."],
        ["Join {company} as a {role} and work on real projects from your first week.",
         "The {company} team has an opening for a {role}."],
        ["{company} is growing and invites applications for the {role} position.",
         "Come build useful things with us: {company} has a {role} opening."],
    ],
    "company_blurb": [
        ["{company} builds {domain} products for customers across India."],
        ["At {company} we create {domain} tools used by growing businesses."],
        ["{company} is a product team focused on {domain}."],
    ],
    "responsibilities": [
        ["You will work closely with a mentor on day-to-day {role_lc} tasks.",
         "Responsibilities include planning your work each week and sharing progress with the team."],
        ["Daily work involves {skill1} and {skill2}, with regular reviews from a senior colleague.",
         "You will document your work and present results to the team every two weeks."],
        ["The role covers hands-on tasks using {skill1}, plus collaboration with other teams.",
         "Expect to own small deliverables and learn how a project moves from idea to release."],
    ],
    "learning": [
        ["We provide structured onboarding and weekly feedback sessions.",
         "You will get access to internal learning material and regular work reviews."],
        ["New joiners are paired with a buddy who answers questions during the first month.",
         "There are monthly knowledge-sharing sessions open to everyone."],
        ["Training covers our tools and working practices during the first two weeks.",
         "You will receive written feedback after every major task."],
    ],
    "culture": [
        ["Our team is small, friendly and focused on steady delivery.",
         "We value clear communication and honest feedback."],
        ["We work in short planning cycles and review progress together.",
         "People here are encouraged to ask questions and share ideas."],
        ["The working style is collaborative with a clear owner for every task.",
         "We keep meetings short and documentation useful."],
    ],
    "benefits_legit": [
        ["Interns receive a certificate and a recommendation letter on successful completion.",
         "Strong performers may be considered for a full-time role."],
        ["Working hours are flexible within the agreed team overlap.",
         "You will have a laptop and tools provided for the duration of the role."],
        ["The team reviews performance regularly and discusses growth paths openly.",
         "Paid leave and public holidays follow the company calendar."],
    ],
    "process_legit": [
        ["Shortlisted candidates are contacted from our official company email for an interview.",
         "The selection process has a screening call followed by a short task discussion."],
        ["Applications are reviewed by our hiring team and every shortlisted candidate receives a reply.",
         "Interviews are scheduled in advance and the panel is introduced before the call."],
        ["Selection involves a brief introduction call and one round with the team lead.",
         "We share the interview schedule by email at least a day before."],
    ],
    "apply_legit": [
        ["To apply, send your resume to the careers address listed on our website."],
        ["Apply through the form on our careers page with your resume and a short note."],
        ["Share your resume and any past work samples through the official application channel."],
    ],
    "no_fee_note": [
        ["There is no registration fee or deposit of any kind at any stage."],
        ["We never charge any processing fee from applicants."],
        ["Applicants are not asked to pay any security deposit."],
    ],
    "req_legit": [
        ["Working knowledge of {skill1} and {skill2}.", "Good written and spoken communication.",
         "Currently pursuing or recently completed a degree in a relevant field.",
         "Ability to learn quickly and work in a team.", "Familiarity with {skill3} is a plus."],
        ["Comfortable using {skill1} for everyday tasks.", "Clear communication with teammates and mentors.",
         "A relevant degree or equivalent project experience.", "Reliable follow-through on deadlines.",
         "Interest in {skill2} and a habit of documenting your work."],
        ["Basic understanding of {skill1} and {skill2}.", "Strong attention to detail and willingness to ask questions.",
         "Available for the full duration of the engagement.", "Able to work independently on small tasks.",
         "Exposure to {skill3} through coursework or projects."],
    ],
    # ---- risky-style text
    "intro_vague": [
        ["Hiring for multiple positions in our growing organisation."],
        ["We have openings for suitable candidates across departments."],
        ["Our firm is recruiting staff for several vacancies."],
    ],
    "hype_pay": [
        ["Earn up to Rs {stipend} per month working only a few hours a day!",
         "Highest stipend in the industry, payout every single month!"],
        ["Make Rs {stipend} every month from the comfort of your home!!",
         "Unbelievable income for simple tasks!"],
        ["Get a monthly income of Rs {stipend} with zero targets.",
         "Amazing earning opportunity, income without limits!"],
    ],
    "no_experience": [
        ["No experience needed, we will train you from scratch."],
        ["No experience required, anyone can join and start earning."],
        ["Freshers, housewives and students are welcome; no experience needed."],
    ],
    "fee": [
        ["Pay a registration fee of Rs {fee} to confirm your seat.",
         "A refundable security deposit of Rs {fee} is required before joining."],
        ["Candidates must pay Rs {fee} as processing charges to receive login details."],
        ["A one-time kit charges of Rs {fee} is payable at the time of enrolment.",
         "Training fee of Rs {fee} will be adjusted against your first stipend."],
    ],
    "personal_data": [
        ["Send your Aadhaar and PAN card photos on WhatsApp for registration."],
        ["Share your bank account details and OTP to activate your payroll profile."],
        ["Submit a photo of ID, Aadhaar number and bank account number to complete verification."],
    ],
    "guaranteed": [
        ["100% placement guaranteed after the programme."],
        ["Guaranteed job offer for every registered candidate."],
        ["Assured selection for all applicants who register today."],
    ],
    "urgency": [
        ["Apply now, limited seats available!"],
        ["Hurry, last date today! Seats filling fast."],
        ["Urgent hiring with immediate joining, apply immediately."],
    ],
    "wfh": [
        ["Work from home with just a phone or laptop."],
        ["Fully remote work, choose your own timings."],
        ["No office visits needed; work from anywhere."],
    ],
    "contact_msg": [
        ["Contact our HR manager on WhatsApp for details."],
        ["Message us on Telegram to receive the joining link."],
        ["For details call or message our HR desk directly."],
    ],
    "mlm": [
        ["Earn commission by referring friends and building your own team.",
         "Every member you add increases your monthly income."],
        ["Grow your network and earn per recruit across multiple levels.",
         "Top team builders unlock higher incentive slabs."],
        ["Join our referral programme, add members and earn from their activity.",
         "Build a downline and earn recurring commission."],
    ],
    "mlm_kit": [
        ["A joining kit worth Rs {fee} is mandatory for all new members."],
        ["New members purchase a starter kit of Rs {fee} to begin."],
        ["The welcome kit costs Rs {fee} and unlocks your referral account."],
    ],
    "offer_letter": [
        ["Your offer letter will be issued immediately after a quick document check.",
         "No interview is required, you are already selected."],
        ["Selected candidates receive an appointment letter within one day.",
         "Your joining letter has been prepared and is waiting for confirmation."],
        ["The offer letter is ready; confirm your details to receive it today.",
         "Candidates are chosen from the submitted profile alone."],
    ],
    "offer_letter_fee": [
        ["The offer letter is released on payment of the stamp paper fee of Rs {fee}."],
        ["Pay Rs {fee} towards ID card charges to receive your appointment letter."],
        ["A documentation fee of Rs {fee} is needed before the joining letter is dispatched."],
    ],
    "vague": [
        ["Opportunity available for suitable candidates.", "Details will be shared later on call."],
        ["Good salary and benefits.", "More information will be given on call."],
        ["Various roles are open.", "The exact role will be shared after registration."],
    ],
    "generic_filler": [
        ["Work timings are flexible.", "Both freshers and experienced people can apply.",
         "Candidates from any city can join.", "Training will be provided by our team."],
        ["The position is open immediately.", "Salary depends on performance.",
         "Many candidates have already joined.", "Support is available throughout the week."],
        ["We are a fast growing organisation.", "Multiple vacancies are available.",
         "Interested people should respond soon.", "Our team will guide you."],
    ],
    "req_risky": [
        ["Own smartphone or laptop with internet.", "Basic typing skills.", "Minimum 18 years of age."],
        ["Willingness to work from home.", "Good communication on WhatsApp.", "Basic computer knowledge."],
        ["Anyone can apply.", "Must be able to start immediately.", "Smartphone with a data connection."],
    ],
    # ---- subtle: polished pattern "flavour" sentences that avoid every strong runtime pattern
    "subtle_advance_fee": [
        ["Some onboarding costs are discussed with selected candidates."],
        ["Selected candidates complete a short enrolment step before the start date."],
        ["Details of the programme contribution are shared after selection."],
    ],
    "subtle_unrealistic_pay": [
        ["Top performers can earn well above the usual range for this role."],
        ["Compensation is highly competitive and linked to results."],
        ["Pay is among the best you will see for this kind of role."],
    ],
    "subtle_data_harvest": [
        ["Candidates should keep their identity documents ready for the onboarding stage."],
        ["Please keep your personal documents handy for a quick profile check."],
        ["A documentation step is completed before the start date."],
    ],
    "subtle_ghost_company": [
        ["Further details are shared with shortlisted candidates."],
        ["The team and project details are explained after selection."],
        ["More about the engagement will be shared during onboarding."],
    ],
    "subtle_mlm_pyramid": [
        ["Team leads can grow into mentoring roles with incentives on team performance."],
        ["Members who bring in new talent receive recognition and rewards."],
        ["There is a referral reward for every successful joiner you introduce."],
    ],
    "subtle_fake_offer_letter": [
        ["Offer letters are issued quickly after a brief document check."],
        ["Selection is fast and the appointment letter follows by message."],
        ["Candidates receive their joining letter soon after profile review."],
    ],
    "mild_urgency": [
        ["Apply now to be considered in the first batch."],
        ["Apply now, as the application window closes this week."],
        ["Apply now so that we can fit you into the earliest cohort."],
    ],
}

HYPE_TITLE_SUFFIXES_WITH_PAY = [" - Earn {stipend} per month!!", " | Earn Rs {stipend} Monthly!", " - Salary {stipend} + Bonus!!"]
HYPE_TITLE_SUFFIXES = [" (Work From Home)", " - URGENT HIRING!", " - Apply Now", " - Earn Big, No Experience Needed", " !!! Work From Home !!!"]


def _export_runtime(backend_data_dir: Path) -> None:
    backend_data_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (("role_benchmarks.json", role_benchmarks_payload()), ("lexicons_runtime.json", RUNTIME_LEXICONS)):
        (backend_data_dir / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {backend_data_dir / name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Export runtime lexicon/benchmark JSON files for inference.")
    ap.add_argument("--export-runtime", action="store_true")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[2] / "backend" / "app" / "data"))
    args = ap.parse_args()
    if args.export_runtime:
        _export_runtime(Path(args.out_dir))
    else:
        ap.print_help()
