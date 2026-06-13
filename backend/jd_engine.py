import re
from openai import OpenAI
import os
import json
import logging

# ✅ STEP 1: API KEY FIX
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
logger = logging.getLogger(__name__)


JD_SKILL_PATTERNS = [
    ("Salesforce", re.compile(r"\bsalesforce\b|\bforce\.com\b", re.I)),
    ("Salesforce Development", re.compile(r"\bsalesforce\s+(?:developer|development|engineering|engineer)\b", re.I)),
    ("Apex", re.compile(r"\bapex\b|\bapex\s+classes?\b|\bapex\s+triggers?\b", re.I)),
    ("Lightning Web Components", re.compile(r"\blightning\s+web\s+components?\b|\blwc\b", re.I)),
    ("Aura Components", re.compile(r"\baura\s+components?\b", re.I)),
    ("Visualforce", re.compile(r"\bvisual\s*force\b|\bvisualforce\b", re.I)),
    ("SOQL", re.compile(r"\bsoql\b", re.I)),
    ("SOSL", re.compile(r"\bsosl\b", re.I)),
    ("Salesforce Flow", re.compile(r"\bsalesforce\s+flows?\b|\bflow\s+builder\b", re.I)),
    ("Salesforce CPQ", re.compile(r"\bsalesforce\s+cpq\b|\bcpq\b", re.I)),
    ("Sales Cloud", re.compile(r"\bsales\s+cloud\b", re.I)),
    ("Service Cloud", re.compile(r"\bservice\s+cloud\b", re.I)),
    ("Salesforce Admin", re.compile(r"\bsalesforce\s+admin(?:istrator)?\b", re.I)),
    ("REST API", re.compile(r"\brest\s+api\b|\brestful\b", re.I)),
    ("GraphQL", re.compile(r"\bgraphql\b", re.I)),
    ("React", re.compile(r"\breact(?:\.js|js)?\b|\breact\s+native\b", re.I)),
    ("Next.js", re.compile(r"\bnext(?:\.js|js)?\b", re.I)),
    ("Vue", re.compile(r"\bvue(?:\.js|js)?\b", re.I)),
    ("Angular", re.compile(r"\bangular\b", re.I)),
    ("Node.js", re.compile(r"\bnode(?:\.js|js)?\b", re.I)),
    ("Express", re.compile(r"\bexpress(?:\.js|js)?\b", re.I)),
    ("Django", re.compile(r"\bdjango\b", re.I)),
    ("FastAPI", re.compile(r"\bfast\s*api\b|\bfastapi\b", re.I)),
    ("PHP", re.compile(r"\bphp\b", re.I)),
    ("Laravel", re.compile(r"\blaravel\b", re.I)),
    ("Spring Boot", re.compile(r"\bspring\s+boot\b", re.I)),
    ("MongoDB", re.compile(r"\bmongo\s*db\b|\bmongodb\b", re.I)),
    ("MySQL", re.compile(r"\bmysql\b", re.I)),
    ("PostgreSQL", re.compile(r"\bpostgres(?:ql)?\b", re.I)),
    ("HTML", re.compile(r"\bhtml5?\b", re.I)),
    ("CSS", re.compile(r"\bcss3?\b", re.I)),
    ("Tailwind CSS", re.compile(r"\btailwind(?:\s+css)?\b", re.I)),
    ("Bootstrap", re.compile(r"\bbootstrap\b", re.I)),
    ("JWT", re.compile(r"\bjwt\b|\bjson\s+web\s+tokens?\b", re.I)),
    ("OAuth", re.compile(r"\boauth\b", re.I)),
    ("Authentication", re.compile(r"\bauth(?:entication)?\b|\blogin\b|\bsign[-\s]?in\b", re.I)),
    ("Authorization", re.compile(r"\bauthori[sz]ation\b", re.I)),
    ("RBAC", re.compile(r"\brbac\b|\brole[-\s]?based\s+access\b", re.I)),
    ("Session Auth", re.compile(r"\bexpress[-\s]?session\b|\bsessions?\b", re.I)),
    ("Firebase Auth", re.compile(r"\bfirebase\s+auth\b", re.I)),
    ("Clerk Auth", re.compile(r"\bclerk\b", re.I)),
    ("Password Hashing", re.compile(r"\bbcrypt\b|\bpassword\s+hash(?:ing)?\b", re.I)),
    ("Git", re.compile(r"\bgit\b", re.I)),
    ("GitHub", re.compile(r"\bgithub\b", re.I)),
    ("GitHub Actions", re.compile(r"\bgithub\s+actions\b", re.I)),
    ("Postman", re.compile(r"\bpostman\b", re.I)),
    ("Selenium", re.compile(r"\bselenium(?:\s+web\s*driver|\s+webdriver)?\b|\bwebdriver\b", re.I)),
    ("Cypress", re.compile(r"\bcypress\b", re.I)),
    ("Playwright", re.compile(r"\bplaywright\b", re.I)),
    ("TestNG", re.compile(r"\btest\s*ng\b|\btestng\b", re.I)),
    ("JUnit", re.compile(r"\bjunit\b", re.I)),
    ("Pytest", re.compile(r"\bpytest\b|\bpy\.?test\b", re.I)),
    ("REST Assured", re.compile(r"\brest[-\s]?assured\b|\brestassured\b", re.I)),
    ("SoapUI", re.compile(r"\bsoap\s*ui\b|\bsoapui\b", re.I)),
    ("API Testing", re.compile(r"\bapi\s+testing\b|\brest\s+api\s+testing\b|\bweb\s+services?\s+testing\b", re.I)),
    ("Manual Testing", re.compile(r"\bmanual\s+testing\b", re.I)),
    ("Automation Testing", re.compile(r"\bautomation\s+testing\b|\btest\s+automation\b|\bqa\s+automation\b", re.I)),
    ("Regression Testing", re.compile(r"\bregression\s+testing\b", re.I)),
    ("Smoke Testing", re.compile(r"\bsmoke\s+testing\b", re.I)),
    ("Sanity Testing", re.compile(r"\bsanity\s+testing\b", re.I)),
    ("Functional Testing", re.compile(r"\bfunctional\s+testing\b", re.I)),
    ("Integration Testing", re.compile(r"\bintegration\s+testing\b", re.I)),
    ("End-to-End Testing", re.compile(r"\bend[-\s]?to[-\s]?end\s+testing\b|\be2e\s+testing\b", re.I)),
    ("Test Cases", re.compile(r"\btest\s+cases?\b|\btest\s+case\s+design\b", re.I)),
    ("Test Plan", re.compile(r"\btest\s+plans?\b", re.I)),
    ("Test Scenarios", re.compile(r"\btest\s+scenarios?\b", re.I)),
    ("Bug Reporting", re.compile(r"\bbug\s+reporting\b|\bdefect\s+reporting\b", re.I)),
    ("Defect Life Cycle", re.compile(r"\bdefect\s+life\s+cycle\b|\bbug\s+life\s+cycle\b|\bdefect\s+lifecycle\b", re.I)),
    ("STLC", re.compile(r"\bstlc\b|\bsoftware\s+testing\s+life\s+cycle\b", re.I)),
    ("SDLC", re.compile(r"\bsdlc\b|\bsoftware\s+development\s+life\s+cycle\b", re.I)),
    ("Jira", re.compile(r"\bjira\b", re.I)),
    ("Jenkins", re.compile(r"\bjenkins\b", re.I)),
    ("GitLab CI", re.compile(r"\bgitlab\s+ci\b", re.I)),
    ("Cucumber", re.compile(r"\bcucumber\b", re.I)),
    ("BDD", re.compile(r"\bbdd\b|\bbehavior[-\s]?driven\s+development\b", re.I)),
    ("JMeter", re.compile(r"\bjmeter\b", re.I)),
    ("Appium", re.compile(r"\bappium\b", re.I)),
    ("Database Testing", re.compile(r"\bdatabase\s+testing\b|\bdb\s+validation\b|\bdatabase\s+validation\b", re.I)),
    ("Vercel", re.compile(r"\bvercel\b", re.I)),
    ("Netlify", re.compile(r"\bnetlify\b", re.I)),
    ("Render", re.compile(r"\brender\b", re.I)),
    ("Heroku", re.compile(r"\bheroku\b", re.I)),
    ("DigitalOcean", re.compile(r"\bdigital\s*ocean\b|\bdigitalocean\b", re.I)),
    ("Nginx", re.compile(r"\bnginx\b", re.I)),
    ("AWS", re.compile(r"\baws\b|\bamazon\s+web\s+services\b", re.I)),
    ("Azure", re.compile(r"\bazure\b", re.I)),
    ("Docker", re.compile(r"\bdocker\b", re.I)),
    ("Kubernetes", re.compile(r"\bkubernetes\b|\bk8s\b", re.I)),
    ("CI/CD", re.compile(r"\bci\s*/\s*cd\b|\bcicd\b|\bcontinuous\s+integration\b", re.I)),
    ("Linux", re.compile(r"\blinux\b", re.I)),
    ("VPS", re.compile(r"\bvps\b|\bvirtual\s+private\s+server\b", re.I)),
    ("Firebase", re.compile(r"\bfirebase\b", re.I)),
    ("Firestore", re.compile(r"\bfirestore\b", re.I)),
    ("Mongoose", re.compile(r"\bmongoose\b", re.I)),
    ("Prisma", re.compile(r"\bprisma\b", re.I)),
    ("Sequelize", re.compile(r"\bsequelize\b", re.I)),
    ("SQL Server", re.compile(r"\bsql\s+server\b", re.I)),
    ("Google Apps Script", re.compile(r"\bgoogle\s+apps?\s+script\b", re.I)),
    ("Power Query", re.compile(r"\bpower\s+query\b", re.I)),
    ("Power BI", re.compile(r"\bpower\s*bi\b|\bpowerbi\b", re.I)),
    ("Excel", re.compile(r"\b(?:(?:ms|microsoft)\s+)?excel\b", re.I)),
    ("SQL", re.compile(r"\bsql(?:\s+queries|\s+query)?\b", re.I)),
    ("Python", re.compile(r"\bpython\b", re.I)),
    ("Pandas", re.compile(r"\bpandas\b", re.I)),
    ("NumPy", re.compile(r"\bnumpy\b|\bnum\s*py\b", re.I)),
    ("Matplotlib", re.compile(r"\bmatplotlib\b", re.I)),
    ("Seaborn", re.compile(r"\bseaborn\b", re.I)),
    ("Tableau", re.compile(r"\btableau\b", re.I)),
    ("DAX", re.compile(r"\bdax\b", re.I)),
    ("JavaScript", re.compile(r"\bjava\s*script\b|\bjavascript\b", re.I)),
    ("Statistics", re.compile(r"\bstatistics?\b", re.I)),
    ("EDA", re.compile(r"\beda\b|\bexploratory\s+data\s+analysis\b", re.I)),
    ("Data Cleaning", re.compile(r"\bdata\s+clean(?:ing)?\b", re.I)),
    ("Data Extraction", re.compile(r"\bdata\s+extract(?:ion)?\b", re.I)),
    ("Data Visualization", re.compile(r"\bdata\s+visuali[sz]ation\b|\bdashboard(?:ing)?\b", re.I)),
    ("Data Analysis", re.compile(r"\bdata\s+analys(?:is|tics)\b|\banalytics?\b", re.I)),
    ("Data Handling", re.compile(r"\bdata\s+handling\b", re.I)),
    ("Problem Solving", re.compile(r"\bproblem\s+solving\b", re.I)),
    ("Communication", re.compile(r"\bcommunication\b", re.I)),
    ("Presentation", re.compile(r"\bpresentation\b", re.I)),
    ("Attention to Detail", re.compile(r"\battention\s+to\s+detail\b", re.I)),
    ("Analytical Thinking", re.compile(r"\banalytical\s+(?:and\s+logical\s+)?thinking\b|\blogical\s+thinking\b", re.I)),
]


def _title_case_skill(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    upper_words = {"sql", "dax", "eda", "api", "aws", "gcp", "ui", "ux"}
    fixed_words = {"numpy": "NumPy", "pandas": "Pandas"}
    words = []

    for word in text.split():
        clean = word.lower()
        if clean in fixed_words:
            words.append(fixed_words[clean])
        elif clean in upper_words:
            words.append(clean.upper())
        else:
            words.append(clean[:1].upper() + clean[1:])

    return " ".join(words)


def _add_unique_skill(result, seen, skill):
    clean = re.sub(r"\s+", " ", str(skill or "")).strip()
    key = clean.lower()
    if clean and key not in seen:
        seen.add(key)
        result.append(clean)


def _normalize_loose_skill_phrase(value):
    text = re.sub(r"[_]", " ", str(value or ""))
    text = re.sub(r"[(){}\[\]]", " ", text)
    text = re.sub(
        r"\b(?:basic|beginner|intermediate|advanced|expert|strong|good|excellent|hands[-\s]?on|required|mandatory|preferred|must\s+have|nice\s+to\s+have|knowledge\s+of|understanding\s+of|familiarity\s+with|experience\s+with|skills?|queries?|query|tools?|concepts?|level|to|and|or|in|with|using)\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"[^\w\s.+#/-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if re.fullmatch(
        r"(quality|reliability|security|reliability security|software quality|high quality|"
        r"problem solving|analytical|communication|team player|fast paced|detail oriented)",
        text,
        re.I,
    ):
        return ""

    if not text or len(text) > 35 or len(text.split()) > 3:
        return ""

    return _title_case_skill(text)


def normalize_jd_skills(skills=None, jd_text=""):
    sources = []

    if isinstance(skills, str):
        sources.extend(re.split(r"[,;|\n]+", skills))
    elif isinstance(skills, list):
        sources.extend(skills)

    if jd_text:
        sources.append(jd_text)

    seen = set()
    result = []

    for source in sources:
        text = str(source or "").strip()
        if not text:
            continue

        matched_known = False
        for label, pattern in JD_SKILL_PATTERNS:
            if pattern.search(text):
                matched_known = True
                _add_unique_skill(result, seen, label)

        if not matched_known:
            _add_unique_skill(result, seen, _normalize_loose_skill_phrase(text))

    return result


# ✅ STEP 2: HELPER FUNCTIONS (TOP LEVEL PE)
def normalize_jd_output(data):
    if isinstance(data, list):
        data = data[0] if data else {}

    if not isinstance(data, dict):
        return {}

    return data


def extract_experience(value):
    if value is None:
        return 0

    if isinstance(value, int):
        return value

    nums = re.findall(r'\d+', str(value))
    if nums:
        return int(nums[0])

    return 0


# ✅ STEP 3: MAIN FUNCTION
def extract_structured_jd(jd_text):
    if not client:
        return {
            "role": "",
            "required_skills": normalize_jd_skills([], jd_text),
            "preferred_skills": [],
            "min_experience_years": extract_experience(jd_text),
            "location": "",
            "education": ""
        }

    prompt = f"""
    Extract structured information from this job description.

    Return ONLY valid JSON.
    Do NOT add explanation.
    Do NOT wrap in markdown.

    STRICT RULES:
    - min_experience_years MUST be an integer (no text like "2-5 years")
    - required_skills and preferred_skills MUST be arrays
    - Skill arrays MUST contain atomic canonical skill/tool names only
    - Do NOT return proficiency or description phrases like "basic to intermediate excel"
    - Example: return "Excel" and "SQL", not "knowledge of sql queries"
    - If data missing, return empty or 0

    Keys required:
    role
    required_skills
    preferred_skills
    min_experience_years
    location
    education

    Job Description:
    {jd_text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Return strictly valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content.strip()

    # Remove markdown if present
    if content.startswith("```"):
        content = content.split("```")[1].strip()

    try:
        data = json.loads(content)

        # ✅ normalize
        data = normalize_jd_output(data)

        # ✅ fix experience
        data["min_experience_years"] = extract_experience(
            data.get("min_experience_years")
        )

        # ✅ fix skills
        data["required_skills"] = normalize_jd_skills(data.get("required_skills") or [], jd_text)
        data["preferred_skills"] = normalize_jd_skills(data.get("preferred_skills") or [])

        # ✅ safe fields
        data["role"] = data.get("role") or ""
        data["location"] = data.get("location") or ""
        data["education"] = data.get("education") or ""

        return data

    except Exception:
        logger.exception("JD parsing failed")

        return {
            "role": "",
            "required_skills": normalize_jd_skills([], jd_text),
            "preferred_skills": [],
            "min_experience_years": 0,
            "location": "",
            "education": ""
        }
