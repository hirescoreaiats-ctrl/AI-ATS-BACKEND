import re
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except ImportError:
    class fuzz:
        @staticmethod
        def token_sort_ratio(left, right):
            left_tokens = " ".join(sorted(str(left or "").split()))
            right_tokens = " ".join(sorted(str(right or "").split()))
            return SequenceMatcher(None, left_tokens, right_tokens).ratio() * 100


SKILL_MAP = {

# programming
"py": "python",
"python3": "python",
"nodejs": "node",
"node.js": "node",
"js": "javascript",
"force com": "salesforce",
"salesforce development": "salesforce",
"salesforce developer": "salesforce",
"lightning web component": "lwc",
"lightning web components": "lwc",
"visual force": "visualforce",
"salesforce flow": "flow",
"flow builder": "flow",
"salesforce cpq": "cpq",

# frontend
"reactjs": "react",
"react.js": "react",
"react js": "react",
"angularjs": "angular",
"angular.js": "angular",

# data tools
"power bi": "powerbi",
"power-bi": "powerbi",
"powerbi": "powerbi",
"tableau": "tableau",
"ms excel": "excel",
"microsoft excel": "excel",

# libraries
"np": "numpy",
"pd": "pandas",

# databases
"postgresql": "sql",
"mysql": "sql",
"sql server": "sql",

# cloud
"amazon web services": "aws",
"aws cloud": "aws",

# ml
"ml": "machine learning",

# security
"penetration testing": "pentesting",
"vulnerability assessment": "vapt"

}


KNOWN_SKILL_PATTERNS = [
    ("salesforce", re.compile(r"\bsalesforce\b|\bforce\.com\b", re.I)),
    ("apex", re.compile(r"\bapex\b|\bapex\s+classes?\b|\bapex\s+triggers?\b", re.I)),
    ("lwc", re.compile(r"\blightning\s+web\s+components?\b|\blwc\b", re.I)),
    ("aura", re.compile(r"\baura\s+components?\b", re.I)),
    ("visualforce", re.compile(r"\bvisual\s*force\b|\bvisualforce\b", re.I)),
    ("soql", re.compile(r"\bsoql\b", re.I)),
    ("sosl", re.compile(r"\bsosl\b", re.I)),
    ("flow", re.compile(r"\b(?:salesforce\s+)?flows?\b|\bflow\s+builder\b", re.I)),
    ("cpq", re.compile(r"\bsalesforce\s+cpq\b|\bcpq\b", re.I)),
    ("powerbi", re.compile(r"\bpower\s*bi\b|\bpowerbi\b", re.I)),
    ("tableau", re.compile(r"\btableau\b", re.I)),
    ("excel", re.compile(r"\b(?:(?:ms|microsoft)\s+)?excel\b", re.I)),
    ("sql", re.compile(r"\bsql(?:\s+queries|\s+query)?\b", re.I)),
    ("python", re.compile(r"\bpython\b", re.I)),
    ("javascript", re.compile(r"\bjava\s*script\b|\bjavascript\b", re.I)),
    ("communication", re.compile(r"\bcommunication\b", re.I)),
    ("presentation", re.compile(r"\bpresentation\b", re.I)),
    ("attention to detail", re.compile(r"\battention\s+to\s+detail\b", re.I)),
    ("analytical thinking", re.compile(r"\banalytical\s+(?:and\s+logical\s+)?thinking\b|\blogical\s+thinking\b", re.I)),
]


TRANSFERABLE_GROUPS = [
    {"powerbi", "tableau", "looker", "qlik"},
    {"excel", "google sheets"},
    {"sql", "postgresql", "mysql", "sql server"},
]


def clean_skill(skill):

    if not skill:
        return ""

    skill = skill.lower().strip()

    skill = re.sub(r"[^\w\s]", " ", skill)
    skill = re.sub(r"\s+", " ", skill)

    return skill


def normalize_skill(skill):

    skill = clean_skill(skill)

    return SKILL_MAP.get(skill, skill)


def normalize_skills(skill_list):

    if not skill_list:
        return []

    normalized = []

    for skill in skill_list:

        clean = normalize_skill(skill)

        if clean:
            normalized.append(clean)

    return list(set(normalized))


def expand_skill_phrase(skill):
    found = [label for label, pattern in KNOWN_SKILL_PATTERNS if pattern.search(str(skill or ""))]
    return found or [normalize_skill(skill)]


def equivalent_skill(left, right):
    if left == right:
        return True

    return any(left in group and right in group for group in TRANSFERABLE_GROUPS)


def match_skills(resume_skills, jd_skills):

    resume_norm = normalize_skills(resume_skills)
    jd_norm = normalize_skills(
        expanded
        for jd_skill in (jd_skills or [])
        for expanded in expand_skill_phrase(jd_skill)
    )

    matched = []
    missing = []

    for jd_skill in jd_norm:

        found = False

        for r_skill in resume_norm:

            # direct match
            if jd_skill in r_skill or r_skill in jd_skill or equivalent_skill(r_skill, jd_skill):
                matched.append(jd_skill)
                found = True
                break

            # fuzzy match
            score = fuzz.token_sort_ratio(jd_skill, r_skill)

            if score > 80:

                matched.append(jd_skill)

                found = True
                break

        if not found:

            missing.append(jd_skill)

    return matched, missing
