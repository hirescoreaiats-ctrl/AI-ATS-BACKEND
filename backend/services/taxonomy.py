import re


SKILL_SYNONYMS = {
    "ai": "Artificial Intelligence",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "php": "PHP",
    "py": "Python",
    "python3": "Python",
    "reactjs": "React",
    "react.js": "React",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "vuejs": "Vue",
    "vue.js": "Vue",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "expressjs": "Express",
    "express.js": "Express",
    "mongodb": "MongoDB",
    "mongo db": "MongoDB",
    "mysql": "MySQL",
    "tailwind": "Tailwind CSS",
    "tailwind css": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    "html5": "HTML",
    "css3": "CSS",
    "html": "HTML",
    "css": "CSS",
    "jwt": "JWT",
    "oauth": "OAuth",
    "auth": "Authentication",
    "authentication": "Authentication",
    "authorization": "Authorization",
    "rbac": "RBAC",
    "session": "Session Auth",
    "express session": "Session Auth",
    "express-session": "Session Auth",
    "firebase auth": "Firebase Auth",
    "clerk": "Clerk Auth",
    "bcrypt": "Password Hashing",
    "password hashing": "Password Hashing",
    "git": "Git",
    "github": "GitHub",
    "github actions": "GitHub Actions",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "postman": "Postman",
    "vercel": "Vercel",
    "netlify": "Netlify",
    "render": "Render",
    "heroku": "Heroku",
    "digitalocean": "DigitalOcean",
    "digital ocean": "DigitalOcean",
    "nginx": "Nginx",
    "vps": "VPS",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mongoose": "Mongoose",
    "firebase": "Firebase",
    "firestore": "Firestore",
    "prisma": "Prisma",
    "sequelize": "Sequelize",
    "sql server": "SQL Server",
    "powerbi": "Power BI",
    "power bi": "Power BI",
    "tableau": "Tableau",
    "pytorch lightning": "PyTorch",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "fast api": "FastAPI",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "aws cloud": "AWS",
    "aws": "AWS",
    "amazon web services": "AWS",
    "sql": "SQL",
    "dax": "DAX",
    "eda": "EDA",
    "kpi": "KPI",
    "gcp": "Google Cloud",
    "azure cloud": "Azure",
    "attention to detail": "Attention to Detail",
    "analytical thinking": "Analytical Thinking",
    "problem solving": "Problem Solving",
    "communication": "Communication",
    "presentation": "Presentation",
    "salesforce": "Salesforce",
    "force.com": "Salesforce",
    "salesforce development": "Salesforce Development",
    "salesforce developer": "Salesforce Development",
    "apex": "Apex",
    "apex classes": "Apex",
    "apex triggers": "Apex",
    "lwc": "Lightning Web Components",
    "lightning web component": "Lightning Web Components",
    "lightning web components": "Lightning Web Components",
    "aura": "Aura Components",
    "aura component": "Aura Components",
    "aura components": "Aura Components",
    "visualforce": "Visualforce",
    "visual force": "Visualforce",
    "soql": "SOQL",
    "sosl": "SOSL",
    "salesforce flow": "Salesforce Flow",
    "flow builder": "Salesforce Flow",
    "salesforce cpq": "Salesforce CPQ",
    "cpq": "Salesforce CPQ",
    "sales cloud": "Sales Cloud",
    "service cloud": "Service Cloud",
    "experience cloud": "Experience Cloud",
    "community cloud": "Experience Cloud",
    "salesforce admin": "Salesforce Admin",
    "salesforce administrator": "Salesforce Admin",
    "data loader": "Data Loader",
    "sfdx": "SFDX",
    "salesforce dx": "SFDX",
    "rest api": "REST API",
    "restful": "REST API",
    "advanced excel": "Advanced Excel",
    "dashboard": "Dashboard",
    "dashboard creation": "Dashboard",
    "mis reporting": "MIS Reporting",
    "kpi": "KPI",
    "kpi reporting": "KPI Reporting",
    "business reporting": "Business Reporting",
    "reporting": "Reporting",
}


TRANSFERABLE_GROUPS = [
    {"FastAPI", "Flask", "Django", "Express", "Spring Boot"},
    {"PostgreSQL", "MySQL", "SQL Server", "Oracle", "SQLite"},
    {"Power BI", "Tableau", "Looker", "Qlik"},
    {"TensorFlow", "PyTorch", "Scikit-learn", "Keras"},
    {"AWS", "Azure", "Google Cloud"},
    {"React", "Angular", "Vue"},
    {"React", "Next.js", "Vue", "Angular"},
    {"Node.js", "Express", "Django", "FastAPI", "Laravel", "Spring Boot"},
    {"MongoDB", "Mongoose"},
    {"Firebase", "Firestore"},
    {"Docker", "Kubernetes", "CI/CD", "GitHub Actions"},
    {"JWT", "OAuth", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Clerk Auth"},
]


SKILL_CATEGORIES = {
    "Python": "Programming",
    "JavaScript": "Programming",
    "TypeScript": "Programming",
    "Java": "Programming",
    "SQL": "Data",
    "PostgreSQL": "Database",
    "MySQL": "Database",
    "FastAPI": "Backend",
    "Flask": "Backend",
    "Django": "Backend",
    "Express": "Backend",
    "Next.js": "Frontend",
    "Vue": "Frontend",
    "Angular": "Frontend",
    "HTML": "Frontend",
    "CSS": "Frontend",
    "Tailwind CSS": "Frontend",
    "Bootstrap": "Frontend",
    "React": "Frontend",
    "Node.js": "Backend",
    "MongoDB": "Database",
    "Power BI": "Analytics",
    "Tableau": "Analytics",
    "Machine Learning": "AI/ML",
    "TensorFlow": "AI/ML",
    "PyTorch": "AI/ML",
    "AWS": "Cloud",
    "Azure": "Cloud",
    "Docker": "DevOps",
    "Kubernetes": "DevOps",
    "Salesforce": "CRM",
    "Salesforce Development": "CRM",
    "Apex": "CRM",
    "Lightning Web Components": "CRM",
    "Aura Components": "CRM",
    "Visualforce": "CRM",
    "SOQL": "CRM",
    "SOSL": "CRM",
    "Salesforce Flow": "CRM",
    "Salesforce CPQ": "CRM",
    "Sales Cloud": "CRM",
    "Service Cloud": "CRM",
    "Experience Cloud": "CRM",
    "Salesforce Admin": "CRM",
    "Data Loader": "CRM",
    "SFDX": "CRM",
    "REST API": "Integration",
    "GraphQL": "Integration",
    "JWT": "Security",
    "OAuth": "Security",
    "Authentication": "Security",
    "Authorization": "Security",
    "RBAC": "Security",
    "Session Auth": "Security",
    "Firebase Auth": "Security",
    "Clerk Auth": "Security",
    "Password Hashing": "Security",
    "Git": "Tools",
    "GitHub": "Tools",
    "GitHub Actions": "DevOps",
    "Postman": "Tools",
    "Vercel": "Cloud",
    "Netlify": "Cloud",
    "Render": "Cloud",
    "Heroku": "Cloud",
    "DigitalOcean": "Cloud",
    "Nginx": "DevOps",
    "VPS": "Cloud",
    "Firebase": "Database",
    "Firestore": "Database",
    "Mongoose": "Database",
    "Prisma": "Database",
    "Sequelize": "Database",
    "SQL Server": "Database",
    "Advanced Excel": "Analytics",
    "Dashboard": "Analytics",
    "MIS Reporting": "Analytics",
    "KPI": "Analytics",
    "KPI Reporting": "Analytics",
    "Business Reporting": "Analytics",
    "Reporting": "Analytics",
}


KNOWN_SKILL_PATTERNS = [
    ("Salesforce", re.compile(r"\bsalesforce\b|\bforce\.com\b", re.I)),
    ("Salesforce Development", re.compile(r"\bsalesforce\s+(?:developer|development|engineering|engineer)\b", re.I)),
    ("Apex", re.compile(r"\bapex\b|\bapex\s+classes?\b|\bapex\s+triggers?\b", re.I)),
    ("Lightning Web Components", re.compile(r"\blightning\s+web\s+components?\b|\blwc\b", re.I)),
    ("Aura Components", re.compile(r"\baura\s+components?\b", re.I)),
    ("Visualforce", re.compile(r"\bvisual\s*force\b|\bvisualforce\b", re.I)),
    ("SOQL", re.compile(r"\bsoql\b", re.I)),
    ("SOSL", re.compile(r"\bsosl\b", re.I)),
    ("Salesforce Flow", re.compile(r"\b(?:salesforce\s+)?flows?\b|\bflow\s+builder\b", re.I)),
    ("Salesforce CPQ", re.compile(r"\bsalesforce\s+cpq\b|\bcpq\b", re.I)),
    ("Sales Cloud", re.compile(r"\bsales\s+cloud\b", re.I)),
    ("Service Cloud", re.compile(r"\bservice\s+cloud\b", re.I)),
    ("Experience Cloud", re.compile(r"\bexperience\s+cloud\b|\bcommunity\s+cloud\b", re.I)),
    ("Salesforce Admin", re.compile(r"\bsalesforce\s+admin(?:istrator)?\b", re.I)),
    ("Data Loader", re.compile(r"\bdata\s+loader\b", re.I)),
    ("SFDX", re.compile(r"\bsfdx\b|\bsalesforce\s+dx\b", re.I)),
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
    ("Vercel", re.compile(r"\bvercel\b", re.I)),
    ("Netlify", re.compile(r"\bnetlify\b", re.I)),
    ("Render", re.compile(r"\brender\b", re.I)),
    ("Heroku", re.compile(r"\bheroku\b", re.I)),
    ("DigitalOcean", re.compile(r"\bdigital\s*ocean\b|\bdigitalocean\b", re.I)),
    ("Nginx", re.compile(r"\bnginx\b", re.I)),
    ("VPS", re.compile(r"\bvps\b|\bvirtual\s+private\s+server\b", re.I)),
    ("CI/CD", re.compile(r"\bci\s*/\s*cd\b|\bcicd\b|\bcontinuous\s+integration\b", re.I)),
    ("Linux", re.compile(r"\blinux\b", re.I)),
    ("Firebase", re.compile(r"\bfirebase\b", re.I)),
    ("Firestore", re.compile(r"\bfirestore\b", re.I)),
    ("Mongoose", re.compile(r"\bmongoose\b", re.I)),
    ("Prisma", re.compile(r"\bprisma\b", re.I)),
    ("Sequelize", re.compile(r"\bsequelize\b", re.I)),
    ("SQL Server", re.compile(r"\bsql\s+server\b", re.I)),
    ("Google Apps Script", re.compile(r"\bgoogle\s+apps?\s+script\b", re.I)),
    ("Power Query", re.compile(r"\bpower\s+query\b", re.I)),
    ("Power BI", re.compile(r"\bpower\s*bi\b|\bpowerbi\b", re.I)),
    ("Advanced Excel", re.compile(r"\badvanced\s+excel\b|\bpivot\s+tables?\b|\bvlookups?\b|\bxlookups?\b|\bmacros?\b|\bvba\b", re.I)),
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
    ("Statistics", re.compile(r"\bstatistics?\b|\bstatistical\b|\bpredictive\s+analytics?\b|\bspss\b|\bsas\b", re.I)),
    ("EDA", re.compile(r"\beda\b|\bexploratory\s+data\s+analysis\b", re.I)),
    ("Data Cleaning", re.compile(r"\bdata\s+clean(?:ing)?\b|\bdata\s+validat(?:e|ion|ing)\b|\breconciliation\b|\bremediation\b", re.I)),
    ("Data Extraction", re.compile(r"\bdata\s+extract(?:ion)?\b|\bextract(?:ed|ion)?\b", re.I)),
    ("Data Visualization", re.compile(r"\bdata\s+visuali[sz]ation\b|\bdashboard(?:ing)?\b", re.I)),
    ("Dashboard", re.compile(r"\bdashboards?\b|\bdashboard\s+creation\b", re.I)),
    ("MIS Reporting", re.compile(r"\bmis\s+report(?:ing|s)?\b", re.I)),
    ("KPI Reporting", re.compile(r"\bkpi\s+report(?:ing|s)?\b", re.I)),
    ("KPI", re.compile(r"\bkpis?\b", re.I)),
    ("Business Reporting", re.compile(r"\bbusiness\s+report(?:ing|s)?\b|\bad[-\s]?hoc\s+report(?:ing|s)?\b", re.I)),
    ("Reporting", re.compile(r"\breport(?:ing|s)?\b", re.I)),
    ("Data Analysis", re.compile(r"\bdata\s+analys(?:is|tics)\b|\banalytics?\b", re.I)),
    ("Data Handling", re.compile(r"\bdata\s+handling\b", re.I)),
    ("Problem Solving", re.compile(r"\bproblem\s+solving\b", re.I)),
    ("Communication", re.compile(r"\bcommunication\b|\bcommunicat(?:e|ed|ing|ion)\b|\bstakeholders?\b|\bclient\s+status\b|\bconferences?\b", re.I)),
    ("Presentation", re.compile(r"\bpresentation\b|\bstorytelling\b|\bpresent(?:ed|ing)?\b", re.I)),
    ("Attention To Detail", re.compile(r"\battention\s+to\s+detail\b|\bdetail-oriented\b|\bvalidation\b|\breconciliation\b", re.I)),
    ("Analytical Thinking", re.compile(r"\banalytical\s+(?:and\s+logical\s+)?thinking\b|\blogical\s+thinking\b|\banaly[sz](?:e|ed|ing)\b", re.I)),
]


def canonical_skill(skill):
    if not skill:
        return ""

    normalized = re.sub(r"[^\w\s\.\+#/-]", " ", str(skill).lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if normalized in SKILL_SYNONYMS:
        return SKILL_SYNONYMS[normalized]

    return " ".join(part.capitalize() for part in normalized.split())


def normalize_skill_list(skills):
    seen = set()
    result = []

    for skill in skills or []:
        canonical = canonical_skill(skill)
        key = canonical.lower()
        if canonical and key not in seen:
            seen.add(key)
            result.append(canonical)

    return _prune_overlapping_skills(result)


def _prune_overlapping_skills(skills):
    labels = {skill.lower() for skill in skills or []}
    remove = set()

    if "kpi reporting" in labels:
        remove.add("kpi")
    if any(label in labels for label in {"mis reporting", "kpi reporting", "business reporting"}):
        remove.add("reporting")
    if "data visualization" in labels:
        remove.add("dashboard")

    return [skill for skill in skills if skill.lower() not in remove]


def known_skills_in_text(value):
    found = []
    text = str(value or "")

    for label, pattern in KNOWN_SKILL_PATTERNS:
        if pattern.search(text):
            found.append(label)

    return normalize_skill_list(found)


def expand_skill_requirements(skills):
    expanded = []

    for skill in skills or []:
        known = known_skills_in_text(skill)
        expanded.extend(known or [canonical_skill(skill)])

    return normalize_skill_list(expanded)


def equivalent_skill(candidate_skill, required_skill):
    candidate = canonical_skill(candidate_skill)
    required = canonical_skill(required_skill)

    if not candidate or not required:
        return False

    if candidate.lower() == required.lower():
        return True

    for group in TRANSFERABLE_GROUPS:
        if candidate in group and required in group:
            return True

    return False


def category_map(skills):
    categories = {}
    for skill in normalize_skill_list(skills):
        category = SKILL_CATEGORIES.get(skill, "Other")
        categories.setdefault(category, []).append(skill)
    return categories


def normalize_designation(title):
    if not title:
        return ""

    title = re.sub(r"\s+", " ", str(title)).strip()
    title = re.sub(r"\bdev\b", "Developer", title, flags=re.I)
    title = re.sub(r"\bswe\b", "Software Engineer", title, flags=re.I)
    title = re.sub(r"\bml engineer\b", "Machine Learning Engineer", title, flags=re.I)

    return title
