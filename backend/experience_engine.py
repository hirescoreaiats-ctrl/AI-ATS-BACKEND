from datetime import datetime
from calendar import monthrange
from dateutil import parser
import re


INVALID_COMPANY_TOKENS = {
    "sql", "python", "excel", "power bi", "tableau", "powerpoint", "microsoft excel",
    "data cleaning", "data visualization", "dashboard", "technical skills", "skills",
    "mis", "loan", "loans", "personal loans",
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
}


def _valid_company_name(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return False
    lowered = text.lower().strip(" :-|")
    if lowered in INVALID_COMPANY_TOKENS:
        return False
    if re.match(r"^[.'’`-]*s\s+technology\b", lowered, re.I):
        return False
    if re.search(r"(https?://|www\.|linkedin|github|portfolio|profile|technical skills|work experience|professional experience|responsibilities)", text, re.I):
        return False
    if re.fullmatch(
        r"(wa|net|us|usa|u\.s\.|u\.s\.a\.|application|html\s+css|java|js|react|node\.?js|"
        r"express\.?js|api|api\s*&|css|sms|machine\s+learning|website|lead|&\s*team\s+lead|"
        r"sde(?:-\d+|\s+\d+)?|senior\s+backend|backend\s+(?:engineer|developer)|"
        r"senior\s+software\s+engineer|software\s+(?:engineer|developer)|elasticseach|elasticsearch)",
        lowered,
        re.I,
    ):
        return False
    if re.fullmatch(r"(uttar\s+pradesh|haryana|gurgaon|gurugram|jaipur|chennai|india|remote|hybrid)", lowered, re.I):
        return False
    if re.search(r"\b(react|node\.?js|express\.?js|html|css|java|python|django|fastapi|api)\b", lowered, re.I) and not re.search(
        r"\b(inc|llc|ltd|limited|private|pvt|corp|corporation|company|services|solutions|technologies|systems|labs|studio|media|group|microsoft|amazon|infosys|capgemini)\b",
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


def process_experience(experience_list):

    processed = []
    date_ranges = []
    raw_ranges = []
    excluded_ranges = []

    for job in experience_list or []:

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

    if latest_job.get("is_current") or latest_job["end"].date() >= datetime.now().date():
        last_working_date = "Present"
    else:
        last_working_date = latest_job["end"].strftime("%b %Y")

    return {

        "total_experience_years": total_experience_years,

        "last_company_name": last_company,

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
