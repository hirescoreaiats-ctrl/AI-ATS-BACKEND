import hashlib
import json
import re

from backend.services.role_taxonomy import detect_role_family, dynamic_core_groups, role_family_default_must_have, role_family_default_nice_to_have
from backend.services.taxonomy import SKILL_CATEGORIES, expand_skill_requirements, known_skills_in_text, normalize_skill_list


JD_PROFILE_VERSION = "jd_profile_v3_dual_mode"

BUSINESS_ANALYST_RESPONSIBILITY_SIGNALS = [
    "requirement gathering",
    "requirement analysis",
    "requirement documentation",
    "business requirements",
    "brd",
    "frd",
    "srs",
    "user stories",
    "use cases",
    "acceptance criteria",
    "functional specification",
    "stakeholder",
    "uat",
    "change request",
    "gap analysis",
    "process flow",
    "workflow",
    "business case",
    "status reports",
    "defect clarification",
]

SENIORITY_PATTERNS = [
    ("architect", r"\b(architect|principal)\b"),
    ("manager", r"\b(manager|head|leadership|people\s+management)\b"),
    ("lead", r"\b(lead|team\s+lead|tech\s+lead)\b"),
    ("senior", r"\b(senior|sr\.?)\b"),
    ("intern", r"\b(intern|internship|trainee)\b"),
    ("junior", r"\b(junior|jr\.?|fresher|entry[-\s]?level)\b"),
    ("mid-level", r"\b(mid[-\s]?level|associate)\b"),
]

DYNAMIC_ROLE_GROUP_RULES = [
    (
        "procurement",
        r"\b(procurement|purchase|purchasing|vendor|supply\s+chain)\b",
        {
            "procurement_process": ["Procurement", "Purchase Orders", "Purchasing"],
            "vendor_management": ["Vendor Management", "Supplier Management", "Negotiation"],
            "erp_tools": ["ERP", "SAP", "Excel"],
            "supply_chain": ["Supply Chain", "Inventory", "Coordination"],
        },
    ),
    (
        "seo",
        r"\b(seo|search\s+engine\s+optimization|keyword\s+research|on[-\s]?page|off[-\s]?page)\b",
        {
            "seo_research": ["Keyword Research", "SEO"],
            "seo_execution": ["On-page SEO", "Off-page SEO", "Content Optimization"],
            "seo_tools": ["Google Search Console", "Google Analytics", "SEMrush", "Ahrefs"],
            "reporting": ["Reporting", "Analytics"],
        },
    ),
    (
        "ui_ux",
        r"\b(ui/ux|ux|user\s+experience|figma|wireframes?|prototypes?|usability)\b",
        {
            "design_tools": ["Figma", "Adobe XD", "Sketch"],
            "interaction_design": ["Wireframes", "Prototypes", "Design Systems"],
            "research_testing": ["User Research", "Usability Testing"],
        },
    ),
]

APPLIED_ML_HYBRID_RE = re.compile(
    r"\b(?:ocr|computer\s+vision|document\s+ai|document\s+intelligence|vlm|vision[-\s]?language|"
    r"multimodal|multi[-\s]?modal|image\s+(?:enhancement|processing|recognition|classification|segmentation)|"
    r"object\s+detection|clip|dino|blip|real[-\s]?esrgan|trocr|paddle\s*ocr|doctr|tesseract|"
    r"form\s+recognition|document\s+vqa|model\s+benchmarking|inference\s+optimization|"
    r"model\s+(?:serving|deployment)|production\s+ml|mlops|llmops|rag|langchain)\b",
    re.I,
)

APPLIED_ML_CORE_GROUPS = {
    "ml_dl_fundamentals": [
        "Machine Learning", "Deep Learning", "Python", "PyTorch", "TensorFlow",
        "Scikit-learn", "Model Evaluation", "Model Benchmarking", "Regression Testing",
    ],
    "cv_ocr_document_ai": [
        "Computer Vision", "OCR", "Document AI", "OpenCV", "Image Processing",
        "Object Detection", "Image Classification", "Segmentation", "YOLO", "R-CNN",
        "PaddleOCR", "Tesseract", "TrOCR", "DocTR", "OMR", "Handwriting Recognition",
        "Label Extraction", "Document VQA", "Image Enhancement", "Real-ESRGAN",
    ],
    "llm_nlp_vlm_multimodal": [
        "NLP", "LLM", "Generative AI", "RAG", "LangChain", "LlamaIndex",
        "Hugging Face", "Transformers", "VLM", "Multimodal AI",
        "Vision-Language Model", "CLIP", "DINO", "BLIP", "vLLM",
        "Fine-tuning", "Prompt Engineering", "Vector Database",
    ],
    "production_ml_mlops": [
        "MLOps", "LLMOps", "MLflow", "Docker", "Kubernetes", "FastAPI",
        "Flask", "Model Deployment", "Model Serving", "Inference Pipeline",
        "CI/CD", "SageMaker", "Vertex AI", "Azure ML", "Monitoring",
        "Latency Optimization", "Cost Optimization", "Production",
    ],
}

PRODUCT_ARCHITECT_RE = re.compile(
    r"\b(?:senior\s+architect|lead\s+architect|product\s+engineering\s+architect|"
    r"software\s+architect|backend\s+architect|technical\s+architect|principal\s+engineer|staff\s+engineer)\b",
    re.I,
)

PRODUCT_ARCHITECT_POSITIVE_RE = re.compile(
    r"\b(product\s+engineering|system\s+design|software\s+architecture|backend\s+architecture|"
    r"api\s+design|distributed\s+systems?|scalab(?:le|ility)|performance|security|"
    r"node(?:\.js)?|python|docker|microservices?|startup|0[-\s]?to[-\s]?1|zero\s+to\s+one|"
    r"b2b\s+saas|ownership|code\s+reviews?|technical\s+leadership|tech\s+lead|mentorship|"
    r"architecture\s+review)\b",
    re.I,
)

PRODUCT_ARCHITECT_CORE_GROUPS = {
    "architecture_system_design": [
        "System Design", "Software Architecture", "Backend Architecture",
        "API Design", "Distributed Systems", "Scalability",
        "Performance Optimization", "Security", "High-scale Systems",
    ],
    "hands_on_backend": [
        "Node.js", "Python", "Express", "FastAPI", "Django", "REST API",
        "SQL", "PostgreSQL", "MongoDB", "Microservices", "Database Design",
    ],
    "devops_delivery": [
        "Docker", "Kubernetes", "CI/CD", "Git", "GitHub Actions",
        "AWS", "Azure", "Cloud Architecture", "Deployment",
    ],
    "product_startup_ownership": [
        "Product Engineering", "Startup Experience", "Product Startup",
        "0-to-1 Product", "B2B SaaS", "Founder Collaboration", "Ownership",
    ],
    "technical_leadership": [
        "Technical Leadership", "Code Review", "Engineering Mentorship",
        "Architecture Review", "Tech Lead", "Mentorship",
    ],
}

M365_MIGRATION_RE = re.compile(
    r"\b(?:microsoft\s+365|m365|office\s+365|o365|collaboration|exchange\s+online|"
    r"tenant[-\s]?to[-\s]?tenant|cross[-\s]?tenant)\s+"
    r"(?:migration\s+)?(?:sme|consultant|engineer|specialist|lead)\b|"
    r"\b(?:microsoft\s+365|m365|office\s+365|o365)\s+migration\b|"
    r"\btenant[-\s]?to[-\s]?tenant\s+migration\b|"
    r"\bexchange\s+(?:online\s+)?migration\b",
    re.I,
)

M365_MIGRATION_POSITIVE_RE = re.compile(
    r"\b(microsoft\s+365\s+migration|m365\s+migration|office\s+365\s+migration|o365\s+migration|"
    r"tenant[-\s]?to[-\s]?tenant\s+migration|cross[-\s]?tenant\s+migration|"
    r"exchange\s+online\s+migration|on[-\s]?prem(?:ises)?\s+exchange\s+migration|"
    r"exchange\s+server\s+migration|teams\s+migration|sharepoint\s+migration|"
    r"onedrive\s+migration|workload\s+migration|mailbox\s+migration|migration\s+batches|"
    r"cutover|coexistence|post[-\s]?migration\s+validation|hypercare|entra\s+id|"
    r"azure\s+ad|quest\s+odm|quest\s+on\s+demand\s+migration|migrationwiz|bittitan|"
    r"sharegate|avepoint|powershell(?:\s+scripting)?|dns\s+cutover|mx\s+records|"
    r"autodiscover|smtp\s+routing)\b",
    re.I,
)

M365_MIGRATION_CORE_GROUPS = {
    "m365_migration": [
        "Microsoft 365 Migration", "Office 365 Migration", "Tenant-to-Tenant Migration",
        "Workload Migration", "Mailbox Migration", "Migration Batches", "Cutover", "Coexistence",
    ],
    "exchange_migration": [
        "Exchange Online Migration", "On-Prem Exchange Migration", "Exchange Online",
        "Exchange Server", "Hybrid Exchange", "Mailbox Migration", "MX Records",
        "Autodiscover", "SMTP Routing",
    ],
    "workload_migration": [
        "Teams Migration", "SharePoint Migration", "OneDrive Migration",
        "Permissions Migration", "Site Migration", "Document Library Migration",
    ],
    "tenant_identity": [
        "Tenant-to-Tenant Migration", "Cross-tenant Migration", "Source Tenant",
        "Target Tenant", "Domain Move", "Identity Mapping", "Entra ID", "Azure AD",
        "Azure AD Connect", "Identity Sync",
    ],
    "tools_scripting": [
        "Quest ODM", "Quest On Demand Migration", "PowerShell Scripting",
        "MigrationWiz", "BitTitan", "ShareGate", "AvePoint", "Microsoft Graph",
    ],
    "seniority_delivery": [
        "SME", "Consultant", "Lead", "Senior Engineer", "Enterprise Migration",
        "Migration Planning", "Cutover Support", "Hypercare", "Post-migration Validation",
        "US Shift",
    ],
}

AML_TM_RE = re.compile(
    r"\b(?:aml\s+transaction\s+monitoring|transaction\s+monitoring)\s+"
    r"(?:investigator|analyst|specialist|officer|l2)\b|"
    r"\baml\s+(?:case\s+)?investigator\b|"
    r"\bfinancial\s+crime\s+investigator\b|"
    r"\baml\s+investigations?\b|"
    r"\baml\s+alerts?\b|"
    r"\bescalated\s+alerts?\b|"
    r"\bsuspicious\s+(?:activity|transaction)\s+(?:review|reporting|investigation)\b|"
    r"\bSAR\s*/\s*STR\b",
    re.I,
)

AML_TM_POSITIVE_RE = re.compile(
    r"\b(aml\s+transaction\s+monitoring|transaction\s+monitoring|tm\s+alerts?|aml\s+alerts?|"
    r"escalated\s+alerts?|alert\s+investigation|transaction\s+review|suspicious\s+transaction\s+monitoring|"
    r"aml\s+investigations?|case\s+(?:investigation|management|handling|review|disposition|closure|narrative)|"
    r"financial\s+crime\s+investigation|money\s+laundering\s+investigation|suspicious\s+(?:activity|transaction)\s+investigation|"
    r"sar|str|suspicious\s+activity\s+report|suspicious\s+transaction\s+report|regulatory\s+reporting|"
    r"retail\s+banking|commercial\s+banking|correspondent\s+banking|source\s+of\s+funds|adverse\s+media|"
    r"smurfing|layering|structuring)\b",
    re.I,
)

AML_TM_CORE_GROUPS = {
    "role_fit": [
        "AML Transaction Monitoring Investigator", "AML Investigator",
        "Transaction Monitoring Investigator", "AML Case Investigator",
        "Financial Crime Investigator", "Senior AML Analyst",
    ],
    "transaction_monitoring": [
        "AML Transaction Monitoring", "Transaction Monitoring", "TM Alerts",
        "AML Alerts", "Monitoring Alerts", "Alert Investigation",
        "Transaction Review", "Suspicious Transaction Monitoring",
    ],
    "aml_investigations": [
        "AML Investigation", "AML Investigations", "Case Investigation",
        "Financial Crime Investigation", "Money Laundering Investigation",
        "Suspicious Activity Investigation", "Suspicious Transaction Investigation",
    ],
    "case_management": [
        "Case Management", "Case Handling", "Case Review", "Case Disposition",
        "Case Closure", "Alert Closure", "Investigation Workflow", "Case Narrative",
    ],
    "sar_str": [
        "SAR", "STR", "Suspicious Activity Report", "Suspicious Transaction Report",
        "SAR Filing", "STR Filing", "SAR Documentation", "STR Documentation",
        "Regulatory Reporting",
    ],
    "banking_exposure": [
        "Retail Banking", "Commercial Banking", "Correspondent Banking",
        "Banking", "Financial Institution", "BFSI",
    ],
    "nice_to_have": [
        "KYC", "CDD", "EDD", "Customer Due Diligence", "Enhanced Due Diligence",
        "Source of Funds", "Source of Wealth", "Adverse Media", "PEP Screening",
        "Sanctions Screening", "Smurfing", "Layering", "Structuring",
        "Money Mule", "Shell Company", "Round Tripping", "Terrorist Financing",
        "US AML", "International AML",
    ],
}


def _is_applied_ml_hybrid(role_title="", jd_text="", skills=None):
    text = " ".join([role_title or "", jd_text or "", " ".join(str(item) for item in skills or [])])
    advanced_hits = {match.group(0).lower() for match in APPLIED_ML_HYBRID_RE.finditer(text)}
    ai_title = bool(re.search(r"\b(data\s+scientist|applied\s+(?:ml|machine\s+learning)|machine\s+learning|ml\s+engineer|ai\s+engineer)\b", text, re.I))
    return ai_title and len(advanced_hits) >= 2


def _is_product_software_architect(role_title="", jd_text="", skills=None):
    text = " ".join([role_title or "", jd_text or "", " ".join(str(item) for item in skills or [])])
    title_hit = bool(PRODUCT_ARCHITECT_RE.search(text))
    positive_hits = {match.group(0).lower() for match in PRODUCT_ARCHITECT_POSITIVE_RE.finditer(text)}
    explicit_product_architect = bool(re.search(r"\barchitect\s*[-/]\s*product\s+engineering\b", text, re.I))
    wrong_domain = bool(re.search(r"\b(civil|construction|building|interior|landscape)\s+architect\b", text, re.I))
    return not wrong_domain and title_hit and (explicit_product_architect or len(positive_hits) >= 4)


def _is_m365_migration_sme(role_title="", jd_text="", skills=None):
    text = " ".join([role_title or "", jd_text or "", " ".join(str(item) for item in skills or [])])
    title_hit = bool(M365_MIGRATION_RE.search(text))
    positive_hits = {match.group(0).lower() for match in M365_MIGRATION_POSITIVE_RE.finditer(text)}
    explicit_title = bool(re.search(r"\b(?:microsoft\s+365|m365|office\s+365|o365)\s+migration\s+sme\b", text, re.I))
    generic_admin_only = bool(re.search(
        r"\b(?:m365|microsoft\s+365|office\s+365|o365|exchange|teams|sharepoint)\s+"
        r"(?:administrator|admin|support)\b",
        text,
        re.I,
    )) and not re.search(r"\bmigration|migrate|tenant[-\s]?to[-\s]?tenant|cutover|coexistence|quest\s+odm\b", text, re.I)
    return not generic_admin_only and (explicit_title or (title_hit and len(positive_hits) >= 3))


def _is_aml_transaction_monitoring(role_title="", jd_text="", skills=None):
    text = " ".join([role_title or "", jd_text or "", " ".join(str(item) for item in skills or [])])
    title_hit = bool(AML_TM_RE.search(text))
    positive_hits = {match.group(0).lower() for match in AML_TM_POSITIVE_RE.finditer(text)}
    kyc_only = bool(re.search(r"\b(kyc|cdd|edd|customer\s+due\s+diligence|enhanced\s+due\s+diligence)\b", text, re.I)) and not re.search(
        r"\b(aml\s+transaction\s+monitoring|transaction\s+monitoring|aml\s+investigations?|aml\s+alerts?|sar|str|suspicious\s+(?:activity|transaction))\b",
        text,
        re.I,
    )
    generic_analyst_only = bool(re.search(
        r"\b(data\s+analyst|business\s+analyst|financial\s+analyst|risk\s+analyst|operations\s+analyst)\b",
        text,
        re.I,
    )) and len(positive_hits) < 3
    return not kyc_only and not generic_analyst_only and (title_hit or len(positive_hits) >= 4)


def _apply_applied_ml_profile(must_have, nice_to_have, jd_text=""):
    explicit = normalize_skill_list(must_have or known_skills_in_text(jd_text or ""))
    grouped = [
        skill
        for options in APPLIED_ML_CORE_GROUPS.values()
        for skill in options
    ]
    must = normalize_skill_list(explicit + grouped[:])
    nice = normalize_skill_list([
        *(nice_to_have or []),
        "Real-ESRGAN", "SDXL", "Whisper", "IndicTrans2", "NLLB",
        "Pinecone", "Chroma", "FAISS", "LoRA", "qLoRA", "Bedrock",
    ])
    nice = [skill for skill in nice if skill.lower() not in {item.lower() for item in must}]
    return must, nice, dict(APPLIED_ML_CORE_GROUPS)


def _apply_product_architect_profile(must_have, nice_to_have, jd_text=""):
    explicit = normalize_skill_list(must_have or known_skills_in_text(jd_text or ""))
    grouped = [
        skill
        for options in PRODUCT_ARCHITECT_CORE_GROUPS.values()
        for skill in options
    ]
    must = normalize_skill_list(explicit + grouped)
    nice = normalize_skill_list([
        *(nice_to_have or []),
        "Kubernetes", "AWS", "Azure", "Redis", "Kafka",
        "Event-driven Architecture", "Observability", "Monitoring",
        "Cost Optimization", "SaaS",
    ])
    nice = [skill for skill in nice if skill.lower() not in {item.lower() for item in must}]
    return must, nice, dict(PRODUCT_ARCHITECT_CORE_GROUPS)


def _apply_m365_migration_profile(must_have, nice_to_have, jd_text=""):
    explicit = normalize_skill_list(must_have or known_skills_in_text(jd_text or ""))
    grouped = [
        skill
        for options in M365_MIGRATION_CORE_GROUPS.values()
        for skill in options
    ]
    must = normalize_skill_list(explicit + grouped)
    nice = normalize_skill_list([
        *(nice_to_have or []),
        "MigrationWiz", "BitTitan", "ShareGate", "AvePoint", "Hybrid Exchange",
        "Conditional Access", "MFA", "Compliance", "Retention", "Microsoft Graph",
    ])
    nice = [skill for skill in nice if skill.lower() not in {item.lower() for item in must}]
    return must, nice, dict(M365_MIGRATION_CORE_GROUPS)


def _apply_aml_transaction_monitoring_profile(must_have, nice_to_have, jd_text=""):
    explicit = normalize_skill_list(must_have or known_skills_in_text(jd_text or ""))
    grouped = [
        skill
        for options in AML_TM_CORE_GROUPS.values()
        for skill in options
    ]
    must = normalize_skill_list(explicit + grouped)
    nice = normalize_skill_list([
        *(nice_to_have or []),
        "AML KYC", "US AML Transaction Monitoring", "International AML Transaction Monitoring",
        "Adverse Media", "Source of Funds", "Source of Wealth",
        "Smurfing", "Layering", "Structuring", "Money Mule",
    ])
    nice = [skill for skill in nice if skill.lower() not in {item.lower() for item in must}]
    return must, nice, dict(AML_TM_CORE_GROUPS)


def _as_list(value):
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\n|]+", value) if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _first_text(*values):
    for value in values:
        if value:
            return str(value).strip()
    return ""


def _stable_hash(payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalized_role_label(role_title, role_family):
    label = re.sub(r"[^a-z0-9]+", "_", str(role_title or role_family or "generic").lower()).strip("_")
    return label or "generic"


def _scoring_mode(role_family, confidence):
    if role_family == "other" or confidence < 55:
        return "dynamic"
    if confidence < 80:
        return "hybrid"
    return "known_template"


def _profile_confidence(mode, role_confidence, must_have, core_groups):
    base = float(role_confidence or 0)
    if mode == "known_template":
        base = max(base, 82)
    elif mode == "hybrid":
        base = min(max(base, 62), 79)
    else:
        base = min(max(base, 45), 74)
    if len(must_have or []) >= 4:
        base += 6
    if len(core_groups or {}) >= 3:
        base += 5
    return round(max(20, min(100, base)), 2)


def _dynamic_core_groups_from_jd(role_title, jd_text, must_have):
    text = f"{role_title or ''}\n{jd_text or ''}\n{' '.join(must_have or [])}".lower()
    for normalized_role, pattern, groups in DYNAMIC_ROLE_GROUP_RULES:
        if re.search(pattern, text, re.I):
            selected = {}
            for group, options in groups.items():
                hits = []
                for option in options:
                    option_pattern = re.escape(option.lower()).replace(r"\ ", r"\s+")
                    if re.search(r"\b" + option_pattern + r"\b", text, re.I):
                        hits.append(option)
                selected[group] = normalize_skill_list(hits or options[:2])
            return normalized_role, selected

    dynamic_skills = normalize_skill_list(must_have or known_skills_in_text(jd_text or ""))
    if dynamic_skills:
        groups = {}
        for index, skill in enumerate(dynamic_skills[:12], start=1):
            key = re.sub(r"[^a-z0-9]+", "_", skill.lower()).strip("_") or f"requirement_{index}"
            groups[key] = [skill]
        return "", groups
    return "", {}


def _dynamic_role_hint(role_title, jd_text):
    text = f"{role_title or ''}\n{jd_text or ''}".lower()
    for normalized_role, pattern, _groups in DYNAMIC_ROLE_GROUP_RULES:
        if re.search(pattern, text, re.I):
            return normalized_role
    return ""


def _title_signals(role_title, role_family):
    tokens = [
        token for token in re.findall(r"[a-z][a-z0-9+#.]{2,}", f"{role_title or ''} {role_family or ''}".lower())
        if token not in {"engineer", "developer", "executive", "associate", "manager", "role"}
    ]
    return sorted(set(tokens))[:8]


def _experience_range(jd_text="", jd_data=None):
    jd_data = jd_data or {}
    min_years = jd_data.get("min_experience_years")
    max_years = jd_data.get("max_experience_years")
    text = " ".join([
        str(jd_text or ""),
        str(jd_data.get("experience_required") or ""),
        str(jd_data.get("experience") or ""),
    ])

    range_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:-|\u2013|\u2014|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
        text,
        re.I,
    )
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        min_years = min_years if min_years is not None else min(low, high)
        max_years = max_years if max_years is not None else max(low, high)

    min_match = re.search(
        r"\b(?:minimum|min|at\s+least)\s+(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
        text,
        re.I,
    )
    if min_match and min_years is None:
        min_years = float(min_match.group(1))

    plus_match = re.search(r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b", text, re.I)
    if plus_match and min_years is None:
        min_years = float(plus_match.group(1))

    return float(min_years or 0), float(max_years or 0)


def _seniority(role_title="", jd_text="", min_years=0):
    text = f"{role_title or ''} {jd_text or ''}".lower()
    for level, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, text, re.I):
            return level
    if min_years >= 8:
        return "lead"
    if min_years >= 5:
        return "senior"
    if min_years >= 2:
        return "mid-level"
    if min_years > 0:
        return "junior"
    return "unknown"


def _explicit_seniority(role_title="", jd_text=""):
    text = f"{role_title or ''} {jd_text or ''}".lower()
    return next((level for level, pattern in SENIORITY_PATTERNS if re.search(pattern, text, re.I)), "")


def _explicit_crm_analytics_requirement(role_title="", jd_text=""):
    text = f"{role_title or ''}\n{jd_text or ''}".lower()
    return bool(re.search(
        r"\b(?:salesforce|crm)\s+(?:data|report(?:ing|s)?|dashboard(?:s)?|analytics?|analyst|administrator|admin)\b|"
        r"\b(?:data|report(?:ing|s)?|dashboard(?:s)?|analytics?)\s+(?:in|on|for|from)\s+(?:salesforce|crm)\b",
        text,
        re.I,
    ))


def _split_analytics_must_have(role_family, role_title, jd_text, must_have):
    if role_family != "data_analytics" or _explicit_crm_analytics_requirement(role_title, jd_text):
        return normalize_skill_list(must_have), []

    filtered = []
    demoted = []
    for skill in normalize_skill_list(must_have):
        if SKILL_CATEGORIES.get(skill) == "CRM":
            demoted.append(skill)
        else:
            filtered.append(skill)
    return filtered, demoted


def _split_full_stack_requirements(role_family, role_title, jd_text, must_have, nice_to_have):
    if role_family != "full_stack":
        return normalize_skill_list(must_have), normalize_skill_list(nice_to_have)

    text = f"{role_title or ''}\n{jd_text or ''}".lower()
    must = normalize_skill_list(must_have)
    nice = normalize_skill_list(nice_to_have)
    analytics_requested = bool(re.search(r"\b(data\s+visuali[sz]ation|analytics\s+dashboard|bi\s+dashboard|reporting\s+dashboard)\b", text, re.I))
    demote = {
        "Data Visualization",
        "Data Analysis",
        "Data Cleaning",
        "Reporting",
        "Dashboard",
        "KPI",
        "KPI Reporting",
        "MIS Reporting",
        "Business Reporting",
    }
    if analytics_requested:
        demote.discard("Dashboard")
        demote.discard("Data Visualization")

    filtered = [skill for skill in must if skill not in demote]
    demoted = [skill for skill in must if skill in demote]
    default_required = role_family_default_must_have("full_stack")
    default_nice = role_family_default_nice_to_have("full_stack")
    filtered = normalize_skill_list(filtered + default_required)
    nice = normalize_skill_list(nice + demoted + [skill for skill in default_nice if skill.lower() not in {item.lower() for item in filtered}])
    return filtered, nice


def _split_dotnet_requirements(role_family, must_have, nice_to_have):
    if role_family != "dotnet_full_stack":
        return normalize_skill_list(must_have), normalize_skill_list(nice_to_have)
    default_required = role_family_default_must_have("dotnet_full_stack")
    default_nice = role_family_default_nice_to_have("dotnet_full_stack")
    required_stack = {
        item.lower()
        for item in default_required
        + [
            ".NET", ".NET Framework", "ASP.NET", "ASP.NET MVC", "ASP.NET Web API",
            "REST API", "RESTful APIs", "Entity Framework", "LINQ", "ADO.NET",
            "AngularJS", "TypeScript", "JavaScript", "HTML", "CSS", "Bootstrap",
            "Kendo UI", "Telerik", "SQL", "MS SQL", "Stored Procedures", "T-SQL",
            "PL/SQL", "SQL Performance Tuning", "Database Optimization",
        ]
    }
    explicit_stack = [skill for skill in must_have or [] if str(skill).lower() in required_stack]
    must = normalize_skill_list(explicit_stack + default_required)
    must_keys = {item.lower() for item in must}
    demoted = [skill for skill in must_have or [] if str(skill).lower() not in must_keys]
    nice = normalize_skill_list((nice_to_have or []) + demoted + [skill for skill in default_nice if skill.lower() not in must_keys])
    return must, nice


DATABASE_REQUIREMENT_RE = re.compile(
    r"\b(sql|mongodb|mongo\s*db|postgres(?:ql)?|mysql|database|schema\s+design|"
    r"query\s+optimization|prisma|supabase)\b",
    re.I,
)


FRONTEND_BACKEND_OPTIONAL = {
    "Node.js", "Express", "MongoDB", "SQL", "PostgreSQL", "MySQL", "SQL Server",
    "Database Design", "Prisma", "Supabase", "Authentication", "Authorization",
    "RBAC", "JWT", "OAuth", "SSO", "OpenID Connect",
}


def _split_frontend_requirements(role_family, role_title, jd_text, must_have, nice_to_have):
    if role_family != "software_frontend":
        return normalize_skill_list(must_have), normalize_skill_list(nice_to_have)

    text = f"{role_title or ''}\n{jd_text or ''}".lower()
    default_required = role_family_default_must_have("software_frontend")
    default_nice = role_family_default_nice_to_have("software_frontend")
    auth_required = _auth_required(role_title, jd_text, must_have, nice_to_have)
    database_required = bool(DATABASE_REQUIREMENT_RE.search(text))

    required = []
    demoted = []
    for skill in normalize_skill_list(must_have or []):
        if skill in FRONTEND_BACKEND_OPTIONAL:
            if skill in {"Authentication", "Authorization", "RBAC", "JWT", "OAuth", "SSO", "OpenID Connect"} and not auth_required:
                demoted.append(skill)
                continue
            if skill in {"MongoDB", "SQL", "PostgreSQL", "MySQL", "SQL Server", "Database Design", "Prisma", "Supabase"} and not database_required:
                demoted.append(skill)
                continue
            if skill in {"Node.js", "Express"} and not re.search(r"\b(required|must|mandatory)\b.{0,80}\b(node(?:\.js)?|express)\b", text, re.I):
                demoted.append(skill)
                continue
        required.append(skill)

    required = normalize_skill_list(required + default_required)
    required_keys = {item.lower() for item in required}
    nice = normalize_skill_list(
        (nice_to_have or [])
        + demoted
        + [skill for skill in default_nice if skill.lower() not in required_keys]
    )
    return required, nice


AUTH_REQUIREMENT_RE = re.compile(
    r"\b(oauth|openid\s+connect|open\s+id\s+connect|oidc|sso|single\s+sign[-\s]?on|"
    r"authentication|authorization|authorisation|rbac|jwt|identity\s+server|azure\s+ad|"
    r"auth\s+flow|secure\s+login|access\s+control)\b",
    re.I,
)


def _auth_required(role_title="", jd_text="", must_have=None, nice_to_have=None):
    text = " ".join([
        str(role_title or ""),
        str(jd_text or ""),
        " ".join(str(item) for item in must_have or []),
        " ".join(str(item) for item in nice_to_have or []),
    ])
    return bool(AUTH_REQUIREMENT_RE.search(text))


def _apply_conditional_auth_groups(core_groups, role_title, jd_text, must_have, nice_to_have):
    groups = dict(core_groups or {})
    if _auth_required(role_title, jd_text, must_have, nice_to_have):
        if "api_auth" in groups:
            groups["api_auth"] = normalize_skill_list([
                skill for skill in groups["api_auth"]
                if skill not in {"REST API", "RESTful APIs", "Web API", "ASP.NET Web API", "GraphQL", "Swagger", "OpenAPI"}
            ] or ["OAuth", "OpenID Connect", "SSO", "Authentication", "Authorization", "JWT", "RBAC"])
        if "auth_security" in groups:
            groups["auth_security"] = normalize_skill_list(groups["auth_security"])
        return groups

    groups.pop("api_auth", None)
    groups.pop("auth_security", None)
    return groups


def _requirement_lines(jd_text=""):
    hard = []
    soft = []
    for raw in re.split(r"[\n\r]+", jd_text or ""):
        line = re.sub(r"\s+", " ", raw).strip(" -:;")
        if not line:
            continue
        lowered = line.lower()
        if re.search(r"\b(must|required|mandatory|min(?:imum)?|should have|need(?:ed)?)\b", lowered):
            hard.append(line[:220])
        elif re.search(r"\b(preferred|nice to have|good to have|plus|communication|team|stakeholder)\b", lowered):
            soft.append(line[:220])
    return hard[:10], soft[:10]


def _critical_must_have_from_jd(jd_text="", must_have=None, hard_requirements=None):
    must_have = normalize_skill_list(must_have or [])
    hard_requirements = hard_requirements or []
    critical = []
    for line in hard_requirements:
        if not re.search(r"\b(must(?:\s+have)?|mandatory|critical|non[-\s]?negotiable)\b", str(line), re.I):
            continue
        for skill in must_have:
            pattern = re.escape(skill).replace(r"\ ", r"\s+")
            if re.search(r"\b" + pattern + r"\b", str(line), re.I):
                critical.append(skill)
    if critical:
        return normalize_skill_list(critical)[:6]

    text = jd_text or ""
    for skill in must_have:
        pattern = re.escape(skill).replace(r"\ ", r"\s+")
        if re.search(
            r"\b(?:must(?:\s+have)?|mandatory|critical|non[-\s]?negotiable)\b.{0,80}\b" + pattern + r"\b|"
            r"\b" + pattern + r"\b.{0,80}\b(?:must(?:\s+have)?|mandatory|critical|non[-\s]?negotiable)\b",
            text,
            re.I,
        ):
            critical.append(skill)
    return normalize_skill_list(critical)[:6]


def _tools_platforms_from_skills(skills):
    tool_categories = {"Cloud", "DevOps", "CRM", "Database", "Testing", "Backend", "Frontend", "Data"}
    found = []
    for skill in normalize_skill_list(skills or []):
        category = SKILL_CATEGORIES.get(skill)
        if category in tool_categories or re.search(r"\b(api|cloud|aws|azure|gcp|docker|kubernetes|jira|git|sql|salesforce|power\s*bi|tableau|excel)\b", skill, re.I):
            found.append(skill)
    return normalize_skill_list(found)[:20]


def _location_work_mode(jd_text="", jd_data=None):
    jd_data = jd_data or {}
    text = " ".join([
        str(jd_data.get("location") or ""),
        str(jd_data.get("work_mode") or ""),
        jd_text or "",
    ])
    work_mode = ""
    if re.search(r"\b(remote|work\s+from\s+home|wfh)\b", text, re.I):
        work_mode = "remote"
    if re.search(r"\bhybrid\b", text, re.I):
        work_mode = "hybrid"
    if re.search(r"\b(onsite|on[-\s]?site|office)\b", text, re.I):
        work_mode = "onsite" if not work_mode else work_mode

    location = jd_data.get("location") or ""
    if not location:
        match = re.search(
            r"\b(?:location|based\s+in|work\s+from)\s*[:\-]?\s*([A-Z][A-Za-z .,-]{2,60})",
            jd_text or "",
        )
        if match:
            location = re.split(r"\n|\.|;", match.group(1))[0].strip(" ,-")
    return str(location or "").strip(), work_mode


def _responsibility_signals(jd_text=""):
    patterns = [
        "develop", "design", "implement", "maintain", "analyze", "report", "dashboard",
        "deploy", "monitor", "support", "sell", "source", "screen", "onboard",
        "reconcile", "audit", "manage", "coordinate", "troubleshoot",
        "test", "automate", "validate", "verify", "debug", "document", "track",
        "regression", "smoke", "sanity", "functional", "integration",
    ]
    found = []
    text = (jd_text or "").lower()
    for word in patterns:
        if re.search(r"\b" + re.escape(word) + r"\w*\b", text):
            found.append(word)
    return found[:12]


def _profile_responsibility_signals(role_family, jd_text=""):
    found = _responsibility_signals(jd_text or "")
    if role_family == "business_analyst":
        text = (jd_text or "").lower()
        ba_found = [
            signal for signal in BUSINESS_ANALYST_RESPONSIBILITY_SIGNALS
            if re.search(r"\b" + re.escape(signal).replace(r"\ ", r"\s+") + r"\b", text, re.I)
        ]
        found = ba_found + [item for item in found if item not in ba_found]
    return found[:20]


def build_jd_profile(jd_text, jd_data=None, jd_skills=None):
    jd_data = jd_data or {}
    role_title = _first_text(jd_data.get("role"), jd_data.get("job_title"), jd_data.get("title"))
    required_skills = expand_skill_requirements(jd_skills or _as_list(jd_data.get("required_skills")))
    nice_skills = expand_skill_requirements(
        _as_list(jd_data.get("preferred_skills") or jd_data.get("nice_to_have_skills"))
    )

    inferred_from_text = known_skills_in_text(jd_text or "")
    must_have = normalize_skill_list(required_skills or inferred_from_text)
    nice_to_have = normalize_skill_list([skill for skill in nice_skills if skill.lower() not in {item.lower() for item in must_have}])

    family_text = " ".join([role_title, jd_text or "", " ".join(must_have), " ".join(nice_to_have)])
    role_family, role_family_confidence = detect_role_family(family_text, must_have + nice_to_have)
    applied_ml_hybrid = _is_applied_ml_hybrid(role_title, jd_text, must_have + nice_to_have)
    product_architect_profile = _is_product_software_architect(role_title, jd_text, must_have + nice_to_have)
    m365_migration_profile = _is_m365_migration_sme(role_title, jd_text, must_have + nice_to_have)
    aml_transaction_monitoring_profile = _is_aml_transaction_monitoring(role_title, jd_text, must_have + nice_to_have)
    applied_ml_core_groups = {}
    product_architect_core_groups = {}
    m365_migration_core_groups = {}
    aml_transaction_monitoring_core_groups = {}
    if applied_ml_hybrid:
        role_family = "applied_ml_engineer"
        role_family_confidence = max(role_family_confidence, 92)
    if product_architect_profile:
        role_family = "product_software_architect"
        role_family_confidence = max(role_family_confidence, 94)
    if m365_migration_profile:
        role_family = "m365_migration_sme"
        role_family_confidence = max(role_family_confidence, 94)
    if aml_transaction_monitoring_profile:
        role_family = "aml_transaction_monitoring"
        role_family_confidence = max(role_family_confidence, 94)
    if role_family == "business_analysis":
        role_family = "business_analyst"
    dynamic_hint = _dynamic_role_hint(role_title, jd_text)
    if dynamic_hint and role_family in {"crm_erp", "other"}:
        role_family = "other"
        role_family_confidence = min(role_family_confidence, 54)
    scoring_mode = _scoring_mode(role_family, role_family_confidence)
    default_must_have = role_family_default_must_have(role_family)
    defaults_applied = False
    if default_must_have and len(must_have) < 3 and role_family_confidence >= 70:
        must_have = normalize_skill_list(must_have + default_must_have)
        nice_to_have = normalize_skill_list([
            skill for skill in nice_to_have
            if skill.lower() not in {item.lower() for item in must_have}
        ])
        defaults_applied = True
    must_have, demoted_must_have = _split_analytics_must_have(role_family, role_title, jd_text, must_have)
    if demoted_must_have:
        nice_to_have = normalize_skill_list(nice_to_have + [
            skill for skill in demoted_must_have
            if skill.lower() not in {item.lower() for item in must_have}
        ])
    must_have, nice_to_have = _split_full_stack_requirements(role_family, role_title, jd_text, must_have, nice_to_have)
    must_have, nice_to_have = _split_dotnet_requirements(role_family, must_have, nice_to_have)
    must_have, nice_to_have = _split_frontend_requirements(role_family, role_title, jd_text, must_have, nice_to_have)
    if role_family == "applied_ml_engineer":
        must_have, nice_to_have, applied_ml_core_groups = _apply_applied_ml_profile(must_have, nice_to_have, jd_text)
    if role_family == "product_software_architect":
        must_have, nice_to_have, product_architect_core_groups = _apply_product_architect_profile(must_have, nice_to_have, jd_text)
    if role_family == "m365_migration_sme":
        must_have, nice_to_have, m365_migration_core_groups = _apply_m365_migration_profile(must_have, nice_to_have, jd_text)
    if role_family == "aml_transaction_monitoring":
        must_have, nice_to_have, aml_transaction_monitoring_core_groups = _apply_aml_transaction_monitoring_profile(must_have, nice_to_have, jd_text)
    min_years, max_years = _experience_range(jd_text, jd_data)
    seniority = _seniority(role_title, jd_text, min_years)
    if role_family == "data_analytics" and seniority in {"senior", "lead"} and not _explicit_seniority(role_title, jd_text):
        seniority = "mid-level" if min_years >= 2 else "unknown"
    hard, soft = _requirement_lines(jd_text)
    core_groups = dynamic_core_groups(role_family, must_have, jd_text or "")
    if applied_ml_core_groups:
        core_groups = applied_ml_core_groups
    if product_architect_core_groups:
        core_groups = product_architect_core_groups
    if m365_migration_core_groups:
        core_groups = m365_migration_core_groups
    if aml_transaction_monitoring_core_groups:
        core_groups = aml_transaction_monitoring_core_groups
    core_groups = _apply_conditional_auth_groups(core_groups, role_title, jd_text, must_have, nice_to_have)
    dynamic_role_label = ""
    if scoring_mode == "dynamic":
        dynamic_role_label, dynamic_groups = _dynamic_core_groups_from_jd(role_title, jd_text, must_have)
        if dynamic_groups:
            core_groups = dynamic_groups
            core_groups = _apply_conditional_auth_groups(core_groups, role_title, jd_text, must_have, nice_to_have)
        if not must_have and core_groups:
            must_have = normalize_skill_list([
                skill
                for options in core_groups.values()
                for skill in (options or [])
            ])
    normalized_role_label = dynamic_role_label or _normalized_role_label(role_title, role_family)
    responsibility_signals = _profile_responsibility_signals(role_family, jd_text or "")
    profile_warnings = []
    if scoring_mode == "dynamic":
        profile_warnings.append("Low role-family confidence; using JD-specific dynamic scoring profile.")
    elif scoring_mode == "hybrid":
        profile_warnings.append("Medium role-family confidence; using calibrated template hints with JD-specific requirements.")
    if defaults_applied:
        profile_warnings.append("Role template defaults applied because JD had too few explicit required skills.")
    if applied_ml_hybrid:
        profile_warnings.append("Hybrid Applied ML profile detected from CV/OCR/LLM/VLM/production ML requirements.")
    if product_architect_profile:
        profile_warnings.append("JD-first Product Software Architect profile detected from product engineering, architecture, backend, Docker, and leadership requirements.")
    if m365_migration_profile:
        profile_warnings.append("JD-first Microsoft 365 Migration SME profile detected; generic M365 admin/support/cloud keywords are not enough for high ranking.")
    if aml_transaction_monitoring_profile:
        profile_warnings.append("JD-first AML Transaction Monitoring profile detected; KYC-only, generic banking, fraud-only, or analyst-only evidence is not enough for high ranking.")
    profile_confidence = _profile_confidence(scoring_mode, role_family_confidence, must_have, core_groups)
    critical_must_have = _critical_must_have_from_jd(jd_text or "", must_have, hard)
    tools_platforms = _tools_platforms_from_skills(must_have + nice_to_have)
    location, work_mode = _location_work_mode(jd_text or "", jd_data)
    domain_keywords = normalize_skill_list([
        item
        for item in [
            role_family if role_family != "other" else "",
            normalized_role_label.replace("_", " "),
            *_as_list(jd_data.get("domain")),
            *_as_list(jd_data.get("industry")),
        ]
        if str(item or "").strip()
    ])
    profile_hash = _stable_hash({
        "role_title": role_title,
        "jd_text": jd_text or "",
        "must_have_skills": must_have,
        "critical_must_have": critical_must_have,
        "nice_to_have_skills": nice_to_have,
        "min_experience_years": min_years,
        "max_experience_years": max_years,
        "profile_version": JD_PROFILE_VERSION,
    })

    return {
        "jd_profile_version": JD_PROFILE_VERSION,
        "profile_jd_hash": profile_hash,
        "role_title": role_title,
        "normalized_role_label": normalized_role_label,
        "role_family": role_family,
        "detected_role_family": role_family,
        "primary_role": (
            "Applied ML Engineer" if role_family == "applied_ml_engineer"
            else "Product Software Architect" if role_family == "product_software_architect"
            else "Microsoft 365 Migration SME" if role_family == "m365_migration_sme"
            else "AML Transaction Monitoring Investigator" if role_family == "aml_transaction_monitoring"
            else role_title
        ),
        "secondary_roles": (
            ["Data Scientist"] if role_family == "applied_ml_engineer" and re.search(r"\bdata\s+scientist\b", family_text, re.I)
            else ["Software Architect", "Backend Architect", "Principal Engineer"] if role_family == "product_software_architect"
            else [
                "M365 Migration Consultant",
                "Office 365 Migration Engineer",
                "Exchange Online Migration Specialist",
                "Tenant-to-Tenant Migration Specialist",
                "Collaboration Migration Engineer",
            ] if role_family == "m365_migration_sme"
            else [
                "AML Investigator",
                "Transaction Monitoring Investigator",
                "AML Case Investigator",
                "Financial Crime Investigator",
                "AML Transaction Monitoring Analyst L2",
                "Senior AML Analyst",
            ] if role_family == "aml_transaction_monitoring"
            else []
        ),
        "role_group": (
            "AI / ML" if role_family == "applied_ml_engineer"
            else "Product Engineering / Software Architecture" if role_family == "product_software_architect"
            else "Microsoft 365 / Collaboration Migration" if role_family == "m365_migration_sme"
            else "AML / Financial Crime Compliance" if role_family == "aml_transaction_monitoring"
            else ""
        ),
        "specialization": (
            ["Computer Vision", "OCR", "Document AI", "LLM/VLM", "Multimodal AI", "Production ML"] if role_family == "applied_ml_engineer"
            else ["System Design", "Backend Architecture", "Product Engineering", "Hands-on Coding", "Technical Leadership"] if role_family == "product_software_architect"
            else ["Tenant-to-Tenant Migration", "Exchange Migration", "Teams/SharePoint/OneDrive Migration", "Quest ODM", "PowerShell"] if role_family == "m365_migration_sme"
            else ["AML Transaction Monitoring", "AML Investigations", "Case Management", "SAR/STR", "Banking Exposure"] if role_family == "aml_transaction_monitoring"
            else []
        ),
        "role_family_confidence": role_family_confidence,
        "scoring_mode": scoring_mode,
        "dynamic_profile_used": scoring_mode == "dynamic",
        "known_template_used": scoring_mode == "known_template",
        "hybrid_profile_used": scoring_mode == "hybrid" or applied_ml_hybrid or product_architect_profile or m365_migration_profile or aml_transaction_monitoring_profile,
        "hybrid_role_detected": bool(applied_ml_hybrid or product_architect_profile or m365_migration_profile or aml_transaction_monitoring_profile or scoring_mode == "hybrid"),
        "profile_confidence": profile_confidence,
        "seniority_level": seniority,
        "min_experience_years": min_years,
        "max_experience_years": max_years,
        "critical_must_have": critical_must_have,
        "must_have": must_have,
        "must_have_skills": must_have,
        "nice_to_have": nice_to_have,
        "nice_to_have_skills": nice_to_have,
        "mandatory_skill_groups": core_groups,
        "preferred_skill_groups": {"preferred": nice_to_have} if nice_to_have else {},
        "core_skill_groups": core_groups,
        "tools_platforms": tools_platforms,
        "domain_keywords": domain_keywords,
        "responsibilities": responsibility_signals,
        "education_requirements": jd_data.get("education") or "",
        "location": location,
        "work_mode": work_mode,
        "red_flags": [],
        "scoring_config_key": role_family if role_family != "other" else "default",
        "backend_groups": {key: value for key, value in core_groups.items() if key in {"backend", "backend_path", "api_logic"}},
        "frontend_groups": {key: value for key, value in core_groups.items() if key in {"frontend", "frontend_foundation", "frontend_core", "react_core", "responsive_ui", "state_management", "frontend_tooling", "performance_debugging"}},
        "database_groups": {key: value for key, value in core_groups.items() if "database" in key},
        "cloud_devops_groups": {key: value for key, value in core_groups.items() if key in {"deployment_tools", "tooling_deployment", "good_to_have"}},
        "auth_security_groups": {key: value for key, value in core_groups.items() if key in {"api_auth", "auth_security"}},
        "tools_process_groups": {key: value for key, value in core_groups.items() if key in {"deployment_tools", "tooling_deployment"}},
        "responsibility_signals": responsibility_signals,
        "responsibility_groups": {"responsibilities": responsibility_signals},
        "title_signals": _title_signals(role_title, role_family),
        "adjacent_title_signals": [],
        "negative_title_signals": [],
        "domain_context": (
            "product software architecture" if role_family == "product_software_architect"
            else "microsoft 365 migration" if role_family == "m365_migration_sme"
            else "aml transaction monitoring investigations" if role_family == "aml_transaction_monitoring"
            else (role_family if role_family != "other" else "")
        ),
        "hard_requirements": hard,
        "soft_requirements": soft,
        "positive_signals": [
            "System Design", "Software Architecture", "Backend Architecture",
            "Node.js or Python", "Docker", "Product/startup ownership",
            "Technical leadership",
        ] if role_family == "product_software_architect" else [
            "Tenant-to-tenant Microsoft 365 migration",
            "Exchange Online or on-prem Exchange migration",
            "Teams, SharePoint, and OneDrive migration",
            "Quest ODM or equivalent migration tooling",
            "PowerShell scripting and cutover validation",
        ] if role_family == "m365_migration_sme" else [
            "AML Transaction Monitoring evidence",
            "AML alert and suspicious transaction investigation",
            "Case management and case narrative documentation",
            "SAR/STR support or suspicious reporting process knowledge",
            "Retail, commercial, or correspondent banking exposure",
        ] if role_family == "aml_transaction_monitoring" else [],
        "negative_signals": [
            "Civil/construction architect", "Cloud-only architect without coding",
            "Enterprise architect without hands-on product engineering",
            "Project/Delivery/Scrum manager", "Generic senior engineer without architecture ownership",
        ] if role_family == "product_software_architect" else [
            "Generic IT support/helpdesk",
            "M365 admin-only users/licenses/mailbox support",
            "Azure infrastructure/cloud-only engineer",
            "SharePoint developer without migration",
            "Project/delivery manager without hands-on migration",
        ] if role_family == "m365_migration_sme" else [
            "Data Analyst or Business Analyst without AML TM evidence",
            "KYC-only profile without AML investigation",
            "Generic banking operations without AML investigation",
            "Fraud-only profile without AML Transaction Monitoring",
            "Compliance officer without case investigation or SAR/STR evidence",
        ] if role_family == "aml_transaction_monitoring" else [],
        "do_not_mix_with": [
            "Civil Architect", "Construction Architect", "Cloud-only Architect",
            "Enterprise Architect without coding", "Project Manager",
            "Delivery Manager", "Scrum Master", "Pure DevOps Engineer",
        ] if role_family == "product_software_architect" else [
            "Helpdesk Support", "Desktop Support", "Generic System Administrator",
            "Azure Cloud Engineer without M365 migration", "M365 Administrator only",
            "SharePoint Developer without migration", "Teams Administrator only",
            "Exchange Administrator without migration", "IAM-only Engineer",
            "Project Manager without hands-on migration",
        ] if role_family == "m365_migration_sme" else [
            "Data Analyst", "Business Analyst", "Financial Analyst", "Risk Analyst",
            "Operations Analyst", "KYC Analyst only", "Customer Support Banking",
            "Loan Officer", "Branch Banking", "Fraud Analyst only",
            "Compliance Officer only",
        ] if role_family == "aml_transaction_monitoring" else [],
        "scoring_weights": (
            {
                "ml_dl_fundamentals": 20,
                "cv_ocr_document_ai": 30,
                "llm_nlp_vlm_multimodal": 25,
                "production_ml_mlops": 20,
                "experience_fit": 5,
            } if role_family == "applied_ml_engineer" else {
                "architecture_system_design": 30,
                "hands_on_backend": 25,
                "product_startup_ownership": 20,
                "technical_leadership": 15,
                "devops_delivery": 5,
                "experience_fit": 5,
            } if role_family == "product_software_architect" else {
                "m365_migration": 25,
                "exchange_migration": 15,
                "workload_migration": 15,
                "tenant_identity": 15,
                "tools_scripting": 15,
                "seniority_delivery": 10,
                "data_quality": 5,
            } if role_family == "m365_migration_sme" else {
                "role_fit": 25,
                "mandatory_aml_tm_skills": 35,
                "experience_fit": 25,
                "banking_domain_exposure": 10,
                "nice_to_have": 5,
            } if role_family == "aml_transaction_monitoring" else {}
        ),
        "score_caps": {},
        "score_boosts": {},
        "profile_warnings": profile_warnings,
        "defaults_applied": defaults_applied,
    }
