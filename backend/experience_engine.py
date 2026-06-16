from datetime import datetime
from calendar import monthrange
from dateutil import parser
import re


INVALID_COMPANY_TOKENS = {
    "sql", "python", "excel", "power bi", "tableau", "powerpoint", "microsoft excel",
    "data cleaning", "data visualization", "dashboard", "technical skills", "skills",
    "mis", "loan", "loans", "personal loans",
    "aml", "aml analyst", "assist aml analyst", "assistant aml analyst",
    "aml analyst ii", "anti-money laundering analyst", "anti money laundering analyst",
    "financial crime analyst", "financial crimes specialist", "transaction monitoring analyst",
    "aml compliance analyst", "kyc analyst", "risk analyst",
    "surat", "gujarat", "maharashtra", "pune", "bengaluru", "bangalore",
    "hyderabad", "chennai", "kolkata", "mumbai", "delhi", "noida",
    "chicago", "chicago il", "pittsburgh", "kirkland", "cresskill", "crm", "remote",
    "sfdc", "gcr", "asean", "greater china region", "market research company",
    "telemarketer", "telesales", "nashville software school",
    "wa", "net", "application", "html css", "java", "react", "node.js", "express.js",
    "react. node.js, express.js", "both node and browser environments",
    "us", "usa", "u.s.", "u.s.a.", "js", "sms", "machine learning", "website",
    "uttar pradesh", "haryana", "gurgaon", "gurugram", "jaipur", "chennai", "india",
    "api", "api &", "lead", "& team lead",
    "sde", "sde-1", "sde 1", "senior backend", "backend engineer", "backend developer",
    "senior software engineer", "software engineer", "software developer", "elasticseach", "elasticsearch",
    "remote qa", "hybrid qa", "resume", "cv", "curriculum vitae", "professional summary",
    "san juan pr senior software testing", "karachi pakistan senior sqa",
    "turkey", "boston ma", "usa remote", "city state", "city state gpa",
    "digitalrealty usa remote", "da ta analy st", "data analyst", "business analyst",
    "assistant manager", "event co-chair", "co-chair",
    "cba", "employment history", "professional experience", "work experience",
    "cms", "seo", "seo web performance", "seo, web performance",
    "frontend", "front end", "front-end", "backend", "api auth", "database",
    "company and its associated businesses", "functionality and improvements",
    "dynamic data driven interfaces", "project evidence", "skill gaps",
    "web performance", "service workers", "tools and best practices", "technologies",
    "projects", "react hook form", "styled components", "style modules", "webpack",
    "github", "frontend engineer with expertise", "summary labels", "csv",
    "api routes", "google share drive", "nodes", "relationships", "nodes and relationships",
    "documentation", "data integration",
    "gpu", "cpu", "nltk", "tensorflow", "pytorch", "opencv", "aws", "azure", "gcp",
    "google cloud", "flask", "fastapi", "pandas", "numpy", "scikit-learn", "scikit learn",
    "langchain", "rag", "llm", "llms", "nlp", "docker", "kubernetes", "publications",
    "publication", "github", "linkedin", "research", "part time", "part-time",
    "london", "canada", "new york", "ahmedabad", "lahore", "pakistan", "atlanta",
    "paris", "sydney", "chicago", "singapore", "sunnyvale", "flask azure and aws vms",
    "senior machine learning", "computer vision", "deep learning", "r-cnn", "rcnn",
    "yolo", "clip", "dino", "blip", "monai", "mri", "ct segmentation",
}

ROLE_ONLY_RE = re.compile(
    r"^(?:senior|sr\.?|junior|jr\.?|lead|principal|staff|technical)?\s*"
    r"(?:qa|sqa|sdet|quality|test|testing|automation|software|digital\s+quality\s+assurance|"
    r"full[-\s]?stack|front[-\s]?end|back[-\s]?end|java|python|web|data|business|bi|mis|"
    r"analytics?|reporting|product|project|technical\s+support|aml|anti[-\s]?money\s+laundering|"
    r"financial\s+crime|financial\s+crimes|transaction\s+monitoring|kyc|risk|compliance)?\s*"
    r"(?:engineer|developer|analyst|consultant|specialist|manager|lead|intern|trainee|"
    r"quality\s+engineer|quality\s+assurance|test\s+lead|technical\s+test\s+lead|"
    r"software\s+testing\s+engineer|automation\s+engineer|qa\s+automation\s+engineer|"
    r"financial\s+crime\s+analyst|financial\s+crimes\s+specialist|transaction\s+monitoring\s+analyst|"
    r"aml\s+compliance\s+analyst)\s*"
    r"(?:\d+|i{1,3}|iv)?$",
    re.I,
)

NON_WORK_EXPERIENCE_RE = re.compile(
    r"\b(summary|profile|skills?|technical\s+skills?|projects?|education|certifications?|"
    r"courses?|coursework|bootcamp|training|achievements?|publications?|portfolio|find\s+me\s+online)\b",
    re.I,
)


def _valid_company_name(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return False
    lowered = text.lower().strip(" :-|")
    if lowered in INVALID_COMPANY_TOKENS:
        return False
    if not re.search(r"[a-zA-Z]{2,}", text):
        return False
    if re.search(r"[\u202a-\u202e\u200e\u200f]", text) and not re.search(r"[a-zA-Z]{2,}", re.sub(r"[\u202a-\u202e\u200e\u200f]", "", text)):
        return False
    if re.fullmatch(
        r"(cms|seo(?:,\s*web\s+performance)?|web\s+performance|service\s+workers?|"
        r"tools\s+and\s+best\s+practices|technologies|projects?|react\s+hook\s+form|"
        r"styled\s+components|style\s+modules|webpack|github|csv|api\s+routes?|"
        r"google\s+share\s+drive|nodes(?:\s+and\s+relationships)?|relationships|documentation|data\s+integration|"
        r"gpu|cpu|nltk|tensorflow|pytorch|opencv|aws|azure|gcp|google\s+cloud|flask|fastapi|"
        r"pandas|numpy|scikit[-\s]?learn|langchain|rag|llms?|nlp|docker|kubernetes|"
        r"publications?|github|linkedin|research|part[-\s]?time|london|canada|new\s+york|"
        r"ahmedabad|lahore|pakistan|atlanta|paris|sydney|chicago|singapore|sunnyvale|"
        r"flask\s+azure\s+and\s+aws\s+vms|senior\s+machine\s+learning|computer\s+vision|"
        r"deep\s+learning|r[-\s]?cnn|yolo|clip|dino|blip|monai|mri|ct\s+segmentation|"
        r"frontend|front[-\s]?end|backend|api\s+auth|database|"
        r"company\s+and\s+its\s+associated\s+businesses|functionality\s+and\s+improvements)",
        lowered,
        re.I,
    ):
        return False
    if ROLE_ONLY_RE.fullmatch(lowered):
        return False
    if re.search(r"\b(senior|sr\.?|lead|assist\.?|assistant)?\s*(qa|sqa|sdet|quality|test|testing|software|data|business|bi|mis|analytics?|reporting|aml|anti[-\s]?money\s+laundering|financial\s+crime|financial\s+crimes|transaction\s+monitoring|kyc|risk|compliance)\s+(engineer|analyst|lead|developer|specialist|investigator)\b", lowered) and not re.search(
        r"\b(inc|llc|ltd|limited|private|pvt|corp|corporation|company|services|solutions|technologies|labs|health|games)\b",
        lowered,
    ):
        return False
    if re.fullmatch(
        r"(remote|hybrid|onsite)?\s*(qa|sqa|sdet|quality\s+assurance|software\s+testing|testing)\b.*",
        lowered,
        re.I,
    ):
        return False
    if re.fullmatch(
        r"[a-z .]+,\s*(?:[a-z]{2}|[a-z .]+)\s+(?:senior\s+|sr\.?\s+|lead\s+)?"
        r"(?:qa|sqa|sdet|quality|test|testing|software)\s+"
        r"(?:(?:engineer|analyst|lead|testing)\b.*)?",
        lowered,
        re.I,
    ):
        return False
    if re.fullmatch(
        r"(?:pakistan|india|usa|u\.s\.a?|sri\s+lanka|san\s+juan|karachi|remote|hybrid)\s+"
        r"(?:senior\s+|sr\.?\s+|lead\s+)?(?:qa|sqa|sdet|quality|test|testing|software)\b.*",
        lowered,
        re.I,
    ):
        return False
    if re.match(r"^[.'’`-]*s\s+technology\b", lowered, re.I):
        return False
    if re.search(r"(https?://|www\.|linkedin|github|portfolio|profile|technical skills|work experience|professional experience|responsibilities)", text, re.I):
        return False
    if re.fullmatch(
        r"(wa|net|us|usa|u\.s\.|u\.s\.a\.|application|html\s+css|java|js|react|node\.?js|"
        r"express\.?js|api|api\s*&|css|sms|machine\s+learning|website|lead|&\s*team\s+lead|"
        r"sde(?:-\d+|\s+\d+)?|senior\s+backend|backend\s+(?:engineer|developer)|"
        r"senior\s+software\s+engineer|software\s+(?:engineer|developer)|elasticseach|elasticsearch|"
        r"react\s+hook\s+form|styled\s+components|style\s+modules|service\s+workers?|webpack|github|"
        r"csv|api\s+routes?|google\s+share\s+drive|nodes|relationships)",
        lowered,
        re.I,
    ):
        return False
    if re.fullmatch(r"(uttar\s+pradesh|haryana|gurgaon|gurugram|jaipur|chennai|india|remote|hybrid)", lowered, re.I):
        return False
    if re.fullmatch(
        r"(turkey|boston\s+ma|usa\s+remote|city\s+state(?:\s+gpa)?|digitalrealty\s+usa\s+remote|"
        r"da\s+ta\s+analy\s+st|event\s+co-chair|co-chair|data\s+analyst|business\s+analyst)",
        lowered,
        re.I,
    ):
        return False
    if re.search(r"\b(react|node\.?js|express\.?js|html|css|java|python|django|fastapi|api|seo|cms|frontend|backend)\b", lowered, re.I) and not re.search(
        r"\b(inc|llc|ltd|limited|private|pvt|corp|corporation|company|services|solutions|technologies|systems|labs|studio|media|group|microsoft|amazon|infosys|capgemini)\b",
        lowered,
        re.I,
    ):
        return False
    if re.search(
        r"\b(gpu|cpu|nltk|tensorflow|pytorch|opencv|aws|azure|gcp|flask|fastapi|pandas|numpy|"
        r"scikit[-\s]?learn|langchain|rag|llms?|nlp|docker|kubernetes|r[-\s]?cnn|yolo|clip|dino|blip|monai)\b",
        lowered,
        re.I,
    ) and not re.search(
        r"\b(inc|llc|ltd|limited|private|pvt|corp|corporation|company|services|solutions|technologies|systems|labs|studio|media|group|microsoft|amazon|infosys|capgemini|nvidia|apple|paypal|qualcomm|kpmg|deloitte)\b",
        lowered,
        re.I,
    ):
        return False
    if re.fullmatch(
        r"(surat|gujarat|maharashtra|pune|bengaluru|bangalore|hyderabad|chennai|kolkata|mumbai|delhi|"
        r"noida|chicago(?:,\s*il)?|pittsburgh|kirkland|cresskill|crm|remote|sfdc|gcr|"
        r"asean|greater china region|market research company|telemarketer|telesales|nashville software school)",
        lowered,
        re.I,
    ):
        return False
    if re.fullmatch(
        r"[A-Za-z .]+,\s*(?:[A-Z]{2}|PA|WA|IL|NJ|CA|NY|TX|FL)(?:\s*\([^)]*\))?",
        text,
        re.I,
    ):
        return False
    if re.match(r"^\d+\s+[A-Za-z0-9 .,'/-]{5,}", text):
        return False
    if len(text.split()) > 8 and not re.search(r"\b(inc|llc|ltd|pvt|private|corp|corporation|company|solutions|systems|technologies|analytics|school|army|bread)\b", text, re.I):
        return False
    if re.search(
        r"\b(implementing|implemented|developing|developed|creating|created|maintaining|optimizing|"
        r"features?|best practices?|dependency|workflow|workflows?)\b",
        text,
        re.I,
    ) and not re.search(
        r"\b(inc|llc|ltd|limited|private|pvt|corp|corporation|company|services|solutions|technologies|"
        r"analytics|consulting|school|university)\b",
        text,
        re.I,
    ):
        return False
    return True


def safe_parse_date(date_str, is_end=False):

    if not date_str:
        return None

    date_str = str(date_str).strip()
    date_str = (
        date_str.replace("‘", "")
        .replace("’", "")
        .replace("`", "")
        .replace("–", "-")
        .replace("—", "-")
    )
    date_str = date_str.replace("’", "'").replace("‘", "'")
    season_match = re.fullmatch(
        r"(summer|winter|spring|autumn|fall)\s*'?\s*(\d{2,4})",
        date_str,
        re.I,
    )
    if season_match:
        season = season_match.group(1).lower()
        year_text = season_match.group(2)
        year = int(year_text if len(year_text) == 4 else f"20{year_text}")
        start_month, end_month = {
            "winter": (1, 2),
            "spring": (3, 5),
            "summer": (6, 8),
            "autumn": (9, 11),
            "fall": (9, 11),
        }[season]
        month = end_month if is_end else start_month
        day = monthrange(year, month)[1] if is_end else 1
        return datetime(year, month, day)

    date_str = re.sub(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s*['\u2018\u2019`]?\s*(\d{2})\b",
        lambda match: f"{match.group(1)} 20{match.group(2)}",
        date_str,
        flags=re.I,
    )

    if date_str.lower() in ["present", "current", "till date"]:
        return datetime.now()

    if re.fullmatch(r"(19|20)\d{2}", date_str):
        year = int(date_str)
        if is_end:
            return datetime(year, 12, 31)
        return datetime(year, 1, 1)

    try:
        parsed = parser.parse(date_str, fuzzy=True)
        if is_end and not re.search(r"\b\d{1,2}\b", date_str):
            last_day = monthrange(parsed.year, parsed.month)[1]
            return parsed.replace(day=last_day)
        return parsed

    except:
        return None


def merge_overlapping_periods(periods):
    """
    Merge overlapping date ranges to avoid double counting
    """

    if not periods:
        return []

    periods.sort(key=lambda x: x[0])

    merged = [periods[0]]

    for current in periods[1:]:

        last = merged[-1]

        if current[0] <= last[1]:

            merged[-1] = (last[0], max(last[1], current[1]))

        else:

            merged.append(current)

    return merged


def _fmt_date(value):
    return value.strftime("%Y-%m-%d") if value else None


def _normalize_company_name(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,-|")
    text = re.sub(r"^(?:employment\s+history|professional\s+experience|work\s+experience)\s+", "", text, flags=re.I).strip(" ,-|")
    text = re.sub(r"^(?:company|employer|client)\s*:\s*", "", text, flags=re.I).strip(" ,-|")
    text = re.sub(r"\s*[-–—]\s*(?:remote|hybrid|onsite|india|usa|u\.s\.a?|pakistan|sri\s+lanka)\s*$", "", text, flags=re.I).strip(" ,-|")
    if "|" in text:
        parts = [part.strip(" .,-|") for part in text.split("|") if part.strip(" .,-|")]
        if parts:
            company_side = parts[0]
            role_side = parts[-1]
            if _valid_company_name(company_side) and (
                re.search(r"\b(qa|sqa|sdet|quality|test|testing|automation|software|engineer|developer|analyst|lead)\b", role_side, re.I)
                or re.fullmatch(
                    r"(?:remote|hybrid|onsite|india|usa|u\.s\.a?|pakistan|sri\s+lanka|"
                    r"hyderabad|chennai|bengaluru|bangalore|pune|mumbai|delhi|noida|kolkata)",
                    role_side,
                    re.I,
                )
            ):
                text = company_side
    dash_parts = [part.strip(" .,-|") for part in re.split(r"\s+(?:-|â€“|â€”|\u2013|\u2014)\s+", text) if part.strip(" .,-|")]
    if len(dash_parts) >= 2:
        left = dash_parts[0]
        right = " - ".join(dash_parts[1:])
        right_role_or_meta = bool(
            re.search(
                r"\b(sde|qa|sqa|sdet|quality|test|testing|automation|software|engineer|developer|"
                r"analyst|lead|consultant|manager|intern|trainee|remote|hybrid|onsite|aml|"
                r"anti[-\s]?money\s+laundering|financial\s+crime|transaction\s+monitoring|kyc|risk|compliance)\b",
                right,
                re.I,
            )
        )
        if _valid_company_name(left) and right_role_or_meta:
            text = left
    comma_parts = [part.strip(" .,-|") for part in re.split(r"\s*[,|]\s*", text) if part.strip(" .,-|")]
    if len(comma_parts) >= 2:
        prefix = " ".join(comma_parts[:-1])
        suffix = comma_parts[-1]
        if re.search(r"\b(qa|sqa|sdet|quality|test|testing|automation|software|engineer|developer|analyst|lead)\b", prefix, re.I):
            text = suffix
        elif re.search(r"\b(qa|sqa|sdet|quality|test|testing|automation|software)\b", suffix, re.I) and re.fullmatch(
            r"[A-Za-z .]+", comma_parts[0]
        ):
            text = suffix
        elif re.search(r"\b(?:us|usa|u\.s\.a?|india|pakistan|sri\s+lanka|pr|[A-Z]{2})\b", suffix, re.I):
            text = comma_parts[0]
    role_prefix = re.match(
        r"^(?:senior\s+|junior\s+|lead\s+)?"
        r"(?:graphic|software|full[-\s]?stack|front[-\s]?end|back[-\s]?end|web|java|python|mern|mean)?\s*"
        r"(?:designer|developer|engineer|intern|trainee|associate|consultant|specialist|manager)\s+"
        r"(?:at|in|with|for)\s+(.+)$",
        text,
        re.I,
    )
    if role_prefix:
        text = role_prefix.group(1).strip(" ,-|")
    return text


def _is_non_work_experience(job):
    if not isinstance(job, dict):
        return True
    section = " ".join(
        str(job.get(key) or "")
        for key in ("section", "section_name", "source_section", "category", "type")
    )
    if section and NON_WORK_EXPERIENCE_RE.search(section):
        return True
    role = str(job.get("role") or job.get("job_title") or "")
    company = str(job.get("company_name") or job.get("company") or "")
    header = " ".join([role, company])
    if re.search(r"\b(bootcamp|coursera|udemy|certification|certificate|coursework|training\s+program)\b", header, re.I):
        if not re.search(r"\b(intern|internship|assistant|employee|employer|worked|work experience|company|analyst|engineer|accountant|developer)\b", header, re.I):
            return True
    if not role and not company:
        return True
    return False


def process_experience(experience_list):

    processed = []
    date_ranges = []
    raw_ranges = []
    excluded_ranges = []

    for job in experience_list or []:
        if _is_non_work_experience(job):
            excluded_ranges.append({
                "company_name": (job or {}).get("company_name") if isinstance(job, dict) else None,
                "role": (job or {}).get("role") if isinstance(job, dict) else None,
                "start_date": (job or {}).get("start_date") if isinstance(job, dict) else None,
                "end_date": (job or {}).get("end_date") if isinstance(job, dict) else None,
                "reason": "non_work_experience_section",
            })
            continue

        raw_end = str(job.get("end_date") or "")
        is_current = raw_end.strip().lower() in ["present", "current", "till date"] or "present" in raw_end.lower()
        start = safe_parse_date(job.get("start_date"))
        end = safe_parse_date(job.get("end_date"), is_end=True)
        raw_record = {
            "company_name": job.get("company_name"),
            "role": job.get("role"),
            "start_date": job.get("start_date"),
            "end_date": job.get("end_date"),
        }

        if not start:
            excluded_ranges.append({**raw_record, "reason": "missing_or_unparseable_start_date"})
            continue

        if datetime.now().year - start.year > 45:
            excluded_ranges.append({**raw_record, "reason": "implausibly_old_start_date"})
            continue

        if not end:
            end = datetime.now()

        now = datetime.now()
        if start > now:
            excluded_ranges.append({**raw_record, "reason": "future_start_date"})
            continue

        if end > now:
            end = now

        if end < start:
            excluded_ranges.append({**raw_record, "reason": "end_before_start"})
            continue

        normalized_company = _normalize_company_name(job.get("company_name"))
        company_name = normalized_company if _valid_company_name(normalized_company) else None
        raw_ranges.append({
            **raw_record,
            "normalized_company_name": company_name,
            "normalized_start": _fmt_date(start),
            "normalized_end": _fmt_date(end),
            "company_valid": bool(company_name),
        })

        processed.append({

            "company_name": company_name,
            "role": job.get("role"),
            "start": start,
            "end": end,
            "is_current": is_current

        })

        date_ranges.append((start, end))

    if not processed:
        return {
            "total_experience_years": 0,
            "last_company_name": None,
            "last_company_confidence": 0.0,
            "last_company_source_text": "",
            "last_company_needs_review": True,
            "last_working_date": None,
            "extracted_date_ranges_raw": raw_ranges,
            "normalized_date_ranges": [],
            "merged_total_experience_ranges": [],
            "excluded_ranges_with_reason": excluded_ranges,
        }

    # latest job detection: current roles win, then latest end/start dates.
    processed.sort(key=lambda x: (1 if x.get("is_current") else 0, x["end"], x["start"]), reverse=True)

    latest_job = next((job for job in processed if job.get("company_name")), processed[0])

    # merge overlapping periods
    merged_periods = merge_overlapping_periods(date_ranges)

    total_days = sum(
        (end - start).days
        for start, end in merged_periods
    )

    total_experience_years = round(total_days / 365, 2)

    last_company = latest_job.get("company_name")
    last_company_confidence = 0.9 if last_company else 0.15
    last_company_needs_review = not bool(last_company)

    if latest_job.get("is_current") or latest_job["end"].date() >= datetime.now().date():
        last_working_date = "Present"
    else:
        last_working_date = latest_job["end"].strftime("%b %Y")

    return {

        "total_experience_years": total_experience_years,

        "last_company_name": last_company,
        "last_company_confidence": last_company_confidence,
        "last_company_source_text": last_company or "",
        "last_company_needs_review": last_company_needs_review,

        "last_working_date": last_working_date,

        "extracted_date_ranges_raw": raw_ranges,

        "normalized_date_ranges": [
            {"start": _fmt_date(start), "end": _fmt_date(end)}
            for start, end in date_ranges
        ],

        "merged_total_experience_ranges": [
            {"start": _fmt_date(start), "end": _fmt_date(end)}
            for start, end in merged_periods
        ],

        "excluded_ranges_with_reason": excluded_ranges,
    }
