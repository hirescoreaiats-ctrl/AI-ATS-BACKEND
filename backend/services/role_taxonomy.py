import re

from backend.services.taxonomy import equivalent_skill, known_skills_in_text, normalize_skill_list


ROLE_FAMILIES = {
    "software_backend": {
        "patterns": [
            r"\bbackend\b",
            r"\bback[-\s]?end\b",
            r"\bpython\s+developer\b",
            r"\bjava\s+developer\b",
            r"\bapi\s+developer\b",
            r"\bnode(?:\.js)?\s+developer\b",
            r"\bspring\s+boot\s+developer\b",
            r"\bsoftware\s+engineer\b",
        ],
        "skills": [
            "Python", "Java", "Node.js", "FastAPI", "Django", "Flask", "Spring Boot",
            "PHP", "Laravel", "SQL", "PostgreSQL", "MySQL", "MongoDB", "REST API",
            "JWT", "OAuth", "Authentication", "Git", "Postman", "Docker", "Linux",
        ],
        "default_must_have": [
            "REST API", "Authentication", "Database Design", "Git", "Postman",
        ],
        "default_core_groups": {
            "backend_path": ["Node.js", "Express", "Python", "Django", "FastAPI", "Flask", "Java", "Spring Boot", "PHP", "Laravel"],
            "api_logic": ["REST API", "GraphQL", "CRUD", "API Integration", "Business Logic"],
            "database": ["SQL", "PostgreSQL", "MySQL", "MongoDB", "SQL Server", "Database Design"],
            "api_auth": ["JWT", "OAuth", "Spring Security", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Auth0", "AWS Cognito", "Clerk Auth", "Password Hashing", "Access Control", "Token Auth", "MFA"],
            "tooling_deployment": ["Git", "GitHub", "Postman", "Swagger", "OpenAPI", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Render", "Nginx", "Linux", "CI/CD"],
            "reliability_security": ["Logging", "Error Handling", "Validation", "Rate Limiting", "Security"],
        },
        "default_nice_to_have": [
            "TypeScript", "Docker", "Redis", "Kafka", "RabbitMQ", "Celery", "BullMQ",
            "CI/CD", "AWS", "Azure", "DigitalOcean", "Nginx", "Linux", "Microservices",
        ],
        "core_groups": {
            "backend_path": ["Node.js", "Express", "Python", "Django", "FastAPI", "Flask", "Java", "Spring Boot", "PHP", "Laravel"],
            "api_logic": ["REST API", "GraphQL", "CRUD", "API Integration", "Business Logic"],
            "database": ["SQL", "PostgreSQL", "MySQL", "MongoDB", "SQL Server", "Database Design"],
            "api_auth": ["JWT", "OAuth", "Spring Security", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Auth0", "AWS Cognito", "Clerk Auth", "Password Hashing", "Access Control", "Token Auth", "MFA"],
            "tooling_deployment": ["Git", "GitHub", "Postman", "Swagger", "OpenAPI", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Render", "Nginx", "Linux", "CI/CD"],
            "reliability_security": ["Logging", "Error Handling", "Validation", "Rate Limiting", "Security"],
        },
    },
    "software_frontend": {
        "patterns": [r"\bfrontend\b", r"\bfront[-\s]?end\b", r"\bui\s+developer\b", r"\breact\s+developer\b"],
        "skills": ["JavaScript", "TypeScript", "React", "Angular", "Vue", "HTML", "CSS"],
        "core_groups": {
            "language": ["JavaScript", "TypeScript"],
            "framework": ["React", "Angular", "Vue"],
            "ui": ["HTML", "CSS", "Responsive Design"],
        },
    },
    "full_stack": {
        "patterns": [
            r"\bfull[-\s]?stack\b",
            r"\bfull\s+stack\s+web\s+developer\b",
            r"\bweb\s+developer\b",
            r"\bmern\b",
            r"\bmean\b",
            r"\breact\b.*\bnode\b|\bnode\b.*\breact\b",
        ],
        "skills": [
            "JavaScript", "TypeScript", "React", "Next.js", "Vue", "Angular", "HTML", "CSS",
            "Node.js", "Express", "Django", "FastAPI", "PHP", "Laravel", "Spring Boot",
            "REST API", "MongoDB", "MySQL", "PostgreSQL", "SQL", "Git", "Docker", "AWS",
        ],
        "default_must_have": ["JavaScript", "React", "Node.js", "REST API", "MongoDB", "SQL", "Git"],
        "default_core_groups": {
            "frontend": ["React", "Next.js", "Vue", "Angular"],
            "frontend_foundation": ["HTML", "CSS", "JavaScript", "TypeScript"],
            "backend": ["Node.js", "Express", "Django", "FastAPI", "PHP", "Laravel", "Java", "Spring Boot"],
            "database": ["MongoDB", "Mongoose", "MySQL", "PostgreSQL", "SQL", "SQL Server", "Firebase", "Firestore", "Prisma", "Sequelize"],
            "api_auth": ["REST API", "GraphQL", "JWT", "OAuth", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Clerk Auth", "Password Hashing"],
            "deployment_tools": ["Git", "GitHub", "GitHub Actions", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Vercel", "Netlify", "Render", "Heroku", "Nginx", "Linux", "VPS", "CI/CD"],
        },
        "default_nice_to_have": [
            "TypeScript", "Next.js", "Docker", "CI/CD", "AWS", "Vercel", "Netlify",
            "DigitalOcean", "Nginx", "Linux", "JWT", "OAuth", "Postman", "Tailwind CSS", "Bootstrap",
        ],
        "core_groups": {
            "frontend": ["React", "Next.js", "Angular", "Vue"],
            "frontend_foundation": ["HTML", "CSS", "JavaScript", "TypeScript"],
            "backend": ["Node.js", "Express", "Python", "Django", "FastAPI", "Flask", "PHP", "Laravel", "Java", "Spring Boot", "REST API"],
            "database": ["SQL", "PostgreSQL", "MySQL", "MongoDB", "Mongoose", "SQL Server", "Firebase", "Firestore", "Prisma", "Sequelize"],
            "api_auth": ["REST API", "GraphQL", "JWT", "OAuth", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Clerk Auth", "Password Hashing"],
            "deployment_tools": ["Git", "GitHub", "GitHub Actions", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Vercel", "Netlify", "Render", "Heroku", "Nginx", "Linux", "VPS", "CI/CD"],
        },
    },
    "mobile_development": {
        "patterns": [r"\bmobile\b", r"\bandroid\b", r"\bios\b", r"\breact\s+native\b", r"\bflutter\b"],
        "skills": ["Android", "iOS", "Kotlin", "Swift", "React Native", "Flutter"],
        "core_groups": {
            "platform": ["Android", "iOS", "React Native", "Flutter"],
            "language": ["Kotlin", "Swift", "Java", "Dart", "JavaScript"],
        },
    },
    "data_analytics": {
        "patterns": [
            r"\bdata\s+analyst\b",
            r"\bmis\s+analyst\b",
            r"\bbi\s+analyst\b",
            r"\bbusiness\s+intelligence\s+analyst\b",
            r"\breporting\s+analyst\b",
            r"\bpower\s*bi\s+(?:analyst|developer)\b",
            r"\banalytics\b",
            r"\breporting\b",
            r"\bdashboards?\b",
        ],
        "skills": [
            "SQL",
            "Excel",
            "Power BI",
            "Tableau",
            "Dashboard",
            "MIS Reporting",
            "KPI",
            "Data Analysis",
            "Data Cleaning",
            "Power Query",
            "DAX",
        ],
        "default_must_have": ["SQL", "Excel", "Data Analysis", "Data Visualization", "Reporting"],
        "default_core_groups": {
            "querying": ["SQL"],
            "spreadsheet": ["Excel", "Advanced Excel"],
            "bi_tool": ["Power BI", "Tableau", "Looker"],
            "reporting": ["MIS Reporting", "Dashboard", "KPI", "Business Reporting", "Reporting"],
        },
        "default_nice_to_have": [
            "Power BI",
            "Tableau",
            "Power Query",
            "DAX",
            "Python",
            "Pandas",
            "Statistics",
            "Data Cleaning",
            "KPI",
            "MIS Reporting",
            "Business Reporting",
        ],
        "core_groups": {
            "querying": ["SQL"],
            "spreadsheet": ["Excel", "Advanced Excel"],
            "bi_tool": ["Power BI", "Tableau", "Looker"],
            "reporting": ["MIS Reporting", "Dashboard", "KPI", "Business Reporting"],
        },
    },
    "data_science": {
        "patterns": [r"\bdata\s+scientist\b", r"\bstatistical\b", r"\bpredictive\b"],
        "skills": ["Python", "SQL", "Statistics", "Machine Learning", "Pandas", "NumPy"],
        "core_groups": {
            "language": ["Python", "R"],
            "statistics": ["Statistics", "Predictive Analytics"],
            "ml": ["Machine Learning", "Scikit-learn"],
            "data": ["SQL", "Pandas", "NumPy"],
        },
    },
    "machine_learning": {
        "patterns": [r"\bmachine\s+learning\b", r"\bml\s+engineer\b", r"\bdeep\s+learning\b", r"\bai\s+engineer\b"],
        "skills": ["Python", "Machine Learning", "TensorFlow", "PyTorch", "Scikit-learn", "MLOps"],
        "core_groups": {
            "language": ["Python"],
            "ml_framework": ["TensorFlow", "PyTorch", "Scikit-learn"],
            "mlops": ["MLOps", "Docker", "Kubernetes", "AWS", "Azure"],
        },
    },
    "devops_cloud": {
        "patterns": [r"\bdevops\b", r"\bsre\b", r"\bcloud\s+engineer\b", r"\bplatform\s+engineer\b"],
        "skills": ["AWS", "Azure", "Google Cloud", "Docker", "Kubernetes", "CI/CD", "Terraform", "Linux"],
        "core_groups": {
            "cloud": ["AWS", "Azure", "Google Cloud"],
            "containers": ["Docker", "Kubernetes"],
            "automation": ["CI/CD", "Terraform", "Jenkins", "GitHub Actions"],
            "systems": ["Linux", "Shell Scripting"],
        },
    },
    "cybersecurity": {
        "patterns": [r"\bcyber\s*security\b", r"\bsecurity\s+analyst\b", r"\bsoc\b", r"\bpenetration\b"],
        "skills": ["Cybersecurity", "SIEM", "SOC", "Vulnerability Assessment", "Penetration Testing"],
        "core_groups": {
            "security_ops": ["SOC", "SIEM", "Incident Response"],
            "assessment": ["Vulnerability Assessment", "Penetration Testing"],
        },
    },
    "salesforce_crm": {
        "patterns": [
            r"\bsalesforce\b",
            r"\bsfdc\b",
            r"\bforce\.com\b",
            r"\bapex\b",
            r"\blwc\b",
            r"\blightning\s+web\s+components?\b",
            r"\bvisualforce\b",
            r"\bsalesforce\s+(?:developer|development|engineer|consultant)\b",
        ],
        "skills": [
            "Salesforce",
            "Salesforce Development",
            "Apex",
            "Lightning Web Components",
            "SOQL",
            "Salesforce Flow",
            "Sales Cloud",
            "Service Cloud",
        ],
        "default_must_have": ["Salesforce", "Salesforce Development", "Apex", "SOQL", "Lightning Web Components"],
        "default_core_groups": {
            "platform": ["Salesforce"],
            "programming": ["Apex", "SOQL"],
            "ui": ["Lightning Web Components", "Aura Components", "Visualforce"],
        },
        "default_nice_to_have": [
            "Salesforce Flow",
            "Sales Cloud",
            "Service Cloud",
            "Experience Cloud",
            "Salesforce CPQ",
            "Aura Components",
            "Visualforce",
            "JavaScript",
            "REST API",
            "Salesforce Admin",
            "Data Loader",
            "SFDX",
        ],
        "core_groups": {
            "platform": ["Salesforce"],
            "programming": ["Apex", "SOQL"],
            "ui": ["Lightning Web Components", "Aura Components", "Visualforce"],
            "automation": ["Salesforce Flow", "Process Builder", "Workflow Rules"],
            "cloud": ["Sales Cloud", "Service Cloud", "Experience Cloud"],
        },
    },
    "crm_erp": {
        "patterns": [r"\bcrm\b", r"\berp\b", r"\bsap\b", r"\boracle\b", r"\bhubspot\b"],
        "skills": ["CRM", "ERP", "SAP", "Oracle", "HubSpot", "Salesforce"],
        "core_groups": {
            "platform": ["CRM", "ERP", "SAP", "Oracle", "HubSpot", "Salesforce"],
            "configuration": ["Configuration", "Customization", "Workflow"],
        },
    },
    "hr_recruitment": {
        "patterns": [r"\bhr\b", r"\brecruit(?:er|ment|ing)\b", r"\btalent\s+acquisition\b", r"\bhuman\s+resources\b"],
        "skills": ["Recruitment", "Sourcing", "Screening", "Onboarding", "Payroll", "ATS", "HRMS"],
        "core_groups": {
            "recruitment": ["Recruitment", "Sourcing", "Screening"],
            "hr_ops": ["Onboarding", "Payroll", "Employee Engagement"],
            "tools": ["ATS", "HRMS"],
        },
    },
    "sales_business_development": {
        "patterns": [r"\bsales\b", r"\bbusiness\s+development\b", r"\blead\s+generation\b", r"\baccount\s+executive\b"],
        "skills": ["Lead Generation", "Cold Calling", "Sales Closing", "CRM", "Communication", "Negotiation"],
        "core_groups": {
            "sales": ["Lead Generation", "Cold Calling", "Sales Closing"],
            "crm": ["CRM", "Salesforce", "HubSpot"],
            "communication": ["Communication", "Negotiation"],
        },
    },
    "digital_marketing": {
        "patterns": [r"\bdigital\s+marketing\b", r"\bseo\b", r"\bsem\b", r"\bsocial\s+media\b", r"\bperformance\s+marketing\b"],
        "skills": ["SEO", "SEM", "Google Ads", "Meta Ads", "Social Media Marketing", "Content Marketing", "Analytics"],
        "core_groups": {
            "channels": ["SEO", "SEM", "Social Media Marketing", "Email Marketing"],
            "ads": ["Google Ads", "Meta Ads"],
            "analytics": ["Google Analytics", "Analytics", "Reporting"],
        },
    },
    "finance_accounting": {
        "patterns": [r"\bfinance\b", r"\baccount(?:ant|ing)\b", r"\bfinancial\s+analyst\b", r"\btax\b", r"\baudit\b"],
        "skills": ["Accounting", "Finance", "Tally", "GST", "Tax", "Audit", "Excel", "Financial Analysis"],
        "core_groups": {
            "accounting": ["Accounting", "Tally", "Bookkeeping"],
            "compliance": ["GST", "Tax", "Audit"],
            "analysis": ["Financial Analysis", "Excel"],
        },
    },
    "customer_support": {
        "patterns": [r"\bcustomer\s+support\b", r"\bcustomer\s+service\b", r"\btechnical\s+support\b", r"\bhelpdesk\b"],
        "skills": ["Customer Support", "Customer Service", "Ticketing", "CRM", "Communication", "Troubleshooting"],
        "core_groups": {
            "support": ["Customer Support", "Customer Service", "Troubleshooting"],
            "tools": ["Ticketing", "CRM", "Zendesk", "Freshdesk"],
            "communication": ["Communication"],
        },
    },
    "project_management": {
        "patterns": [r"\bproject\s+manager\b", r"\bprogram\s+manager\b", r"\bscrum\b", r"\bagile\b"],
        "skills": ["Project Management", "Agile", "Scrum", "Jira", "Stakeholder Management"],
        "core_groups": {
            "delivery": ["Project Management", "Program Management"],
            "methodology": ["Agile", "Scrum"],
            "tools": ["Jira", "MS Project"],
        },
    },
    "product_management": {
        "patterns": [r"\bproduct\s+manager\b", r"\bproduct\s+owner\b", r"\broadmap\b", r"\buser\s+stories\b"],
        "skills": ["Product Management", "Roadmap", "User Stories", "Market Research", "Analytics"],
        "core_groups": {
            "product": ["Product Management", "Roadmap", "User Stories"],
            "discovery": ["Market Research", "User Research"],
            "analytics": ["Analytics", "Metrics"],
        },
    },
    "business_analysis": {
        "patterns": [r"\bbusiness\s+analyst\b", r"\brequirements?\s+gathering\b", r"\bbrd\b", r"\bfrd\b"],
        "skills": ["Business Analysis", "Requirements Gathering", "BRD", "FRD", "SQL", "Stakeholder Management"],
        "core_groups": {
            "analysis": ["Business Analysis", "Requirements Gathering"],
            "documentation": ["BRD", "FRD", "User Stories"],
            "data": ["SQL", "Excel"],
        },
    },
    "operations": {
        "patterns": [r"\boperations?\b", r"\bprocess\s+improvement\b", r"\bback\s+office\b"],
        "skills": ["Operations", "Process Improvement", "Excel", "Reporting", "Coordination"],
        "core_groups": {
            "operations": ["Operations", "Process Improvement", "Coordination"],
            "reporting": ["Excel", "Reporting"],
        },
    },
}


FAMILY_ALIASES = set(ROLE_FAMILIES) | {"other"}


def role_family_core_groups(role_family):
    return dict((ROLE_FAMILIES.get(role_family) or {}).get("core_groups") or {})


def role_family_default_must_have(role_family):
    return normalize_skill_list((ROLE_FAMILIES.get(role_family) or {}).get("default_must_have") or [])


def role_family_default_core_groups(role_family):
    return dict((ROLE_FAMILIES.get(role_family) or {}).get("default_core_groups") or {})


def role_family_default_nice_to_have(role_family):
    return normalize_skill_list((ROLE_FAMILIES.get(role_family) or {}).get("default_nice_to_have") or [])


def detect_role_family(text, skills=None):
    combined = f"{text or ''} {' '.join(str(item) for item in skills or [])}".lower()
    best_family = "other"
    best_score = 0

    for family, config in ROLE_FAMILIES.items():
        score = 0
        for pattern in config.get("patterns") or []:
            if re.search(pattern, combined, re.I):
                score += 5
        family_skills = normalize_skill_list(config.get("skills") or [])
        input_skills = normalize_skill_list(skills or [])
        for skill in input_skills:
            if any(skill.lower() == item.lower() or equivalent_skill(skill, item) for item in family_skills):
                score += 3
        if score > best_score:
            best_family = family
            best_score = score

    confidence = min(100, 25 + best_score * 10) if best_score else 20
    return best_family, confidence


def dynamic_core_groups(role_family, jd_skills=None, jd_text=""):
    base_groups = role_family_core_groups(role_family)
    jd_skill_list = normalize_skill_list((jd_skills or []) + known_skills_in_text(jd_text or ""))
    text = f"{jd_text or ''} {' '.join(jd_skill_list)}".lower()
    selected = {}

    for group, options in base_groups.items():
        mentions = []
        for skill in options:
            skill_pattern = re.escape(str(skill).lower()).replace(r"\ ", r"\s+")
            if re.search(r"\b" + skill_pattern + r"\b", text, re.I):
                mentions.append(skill)
            elif any(equivalent_skill(skill, jd_skill) for jd_skill in jd_skill_list):
                mentions.append(skill)
        if mentions:
            selected[group] = normalize_skill_list(mentions)

    default_groups = role_family_default_core_groups(role_family)
    if default_groups and len(selected) < 3:
        return default_groups

    if not selected and jd_skill_list:
        selected["jd_required_skills"] = jd_skill_list[:8]

    return selected


def match_core_skill_groups(core_skill_groups, candidate_skills=None, resume_text=""):
    candidate_skills = normalize_skill_list(candidate_skills or [])
    resume_skills = normalize_skill_list(known_skills_in_text(resume_text or ""))
    all_skills = normalize_skill_list(candidate_skills + resume_skills)
    text = (resume_text or "").lower()
    matched = {}
    missing = []

    for group, required_options in (core_skill_groups or {}).items():
        group_hits = []
        for required in normalize_skill_list(required_options or []):
            pattern = re.escape(required.lower()).replace(r"\ ", r"\s+")
            direct_text = bool(re.search(r"\b" + pattern + r"\b", text, re.I))
            skill_hit = any(
                required.lower() == skill.lower() or equivalent_skill(skill, required)
                for skill in all_skills
            )
            if direct_text or skill_hit:
                group_hits.append(required)
        if group_hits:
            matched[group] = normalize_skill_list(group_hits)
        else:
            missing.append(group)

    total = max(len(core_skill_groups or {}), 1)
    percent = round((len(matched) / total) * 100, 2) if core_skill_groups else 0.0
    return {
        "core_skill_match_percent": percent,
        "matched_core_skill_groups": matched,
        "missing_core_skill_groups": missing,
    }
