from backend.jd_engine import normalize_jd_skills
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


M365_JD = """
Microsoft 365 Migration SME. Experience 8-10 years. US shift.
The role requires hands-on Microsoft 365 / Office 365 tenant-to-tenant migration
ownership for enterprise environments. Must have Exchange Online migration,
On-Prem Exchange to Exchange Online migration, Teams migration, SharePoint migration,
OneDrive migration, Entra ID / Azure AD tenant identity mapping, PowerShell scripting,
Quest ODM or equivalent migration tooling, migration batches, coexistence, cutover,
post-migration validation, and hypercare. Do not mix this with generic helpdesk,
M365 administrator-only, Azure infrastructure-only, SharePoint developer, IAM-only,
or project manager profiles without hands-on migration execution.
"""


def m365_profile(jd=M365_JD, role="Microsoft 365 Migration SME"):
    skills = normalize_jd_skills([], jd)
    return build_jd_profile(jd, {"role": role, "experience_required": "8-10 years"}, skills)


def score_m365(parsed, jd=M365_JD, role="Microsoft 365 Migration SME"):
    profile = m365_profile(jd, role)
    resume_text = " ".join([
        str(parsed.get("designation") or ""),
        " ".join(str(skill) for skill in parsed.get("key_skills") or []),
        " ".join(
            str(exp.get("role") or "") + " " + str(exp.get("description") or "")
            for exp in parsed.get("experience") or []
        ),
        " ".join(str(project.get("description") or "") for project in parsed.get("projects") or []),
    ])
    parsed.update(estimate_relevant_experience_v2(parsed, resume_text, profile))
    return profile, score_candidate(
        parsed,
        jd,
        profile["must_have_skills"],
        {"role": role, "experience_required": "8-10 years"},
        resume_text,
        jd_profile=profile,
    )


def test_m365_jd_profile_is_isolated_and_migration_specific():
    profile = m365_profile()

    assert profile["role_family"] == "m365_migration_sme"
    assert profile["primary_role"] == "Microsoft 365 Migration SME"
    assert "M365 Migration Consultant" in profile["secondary_roles"]
    assert "m365_migration" in profile["core_skill_groups"]
    assert "tenant_identity" in profile["core_skill_groups"]
    assert "Helpdesk Support" in profile["do_not_mix_with"]
    assert any("Tenant-to-tenant" in signal for signal in profile["positive_signals"])
    assert profile["profile_jd_hash"]


def test_strong_m365_migration_sme_scores_high():
    parsed = {
        "full_name": "Strong M365 SME",
        "designation": "Microsoft 365 Migration SME",
        "key_skills": [
            "Microsoft 365 Migration", "Tenant-to-Tenant Migration", "Exchange Online Migration",
            "On-Prem Exchange Migration", "Teams Migration", "SharePoint Migration",
            "OneDrive Migration", "Quest ODM", "PowerShell Scripting", "Azure AD", "Entra ID",
        ],
        "total_experience_years": 9,
        "experience": [{
            "company_name": "Enterprise Migration Partner",
            "role": "Microsoft 365 Migration SME",
            "start_date": "Jan 2017",
            "end_date": "Jan 2026",
            "description": (
                "Led enterprise Microsoft 365 migration and tenant-to-tenant migration programs. "
                "Executed On-Prem Exchange to Exchange Online migration, mailbox migration batches, "
                "Teams migration, SharePoint migration, and OneDrive migration using Quest ODM. "
                "Created PowerShell scripting automation for source tenant to target tenant identity "
                "mapping with Entra ID and Azure AD Connect. Owned coexistence, DNS cutover, MX records, "
                "Autodiscover, post-migration validation, hypercare, and US shift cutover support."
            ),
        }],
        "projects": [],
        "resume_quality_score": 92,
    }

    _, result = score_m365(parsed)

    assert result["final_score"] >= 82
    assert result["label"] == "Strong Match"
    assert result["recommendation"] == "shortlisted"
    assert not result["missing_core_skill_groups"]


def test_m365_admin_without_migration_is_not_high():
    parsed = {
        "full_name": "M365 Admin",
        "designation": "Microsoft 365 Administrator",
        "key_skills": ["Microsoft 365", "Azure AD", "Exchange Online", "Teams", "SharePoint", "User Management"],
        "total_experience_years": 9,
        "experience": [{
            "company_name": "IT Operations",
            "role": "M365 Administrator",
            "description": (
                "Managed Microsoft 365 users, licenses, mailboxes, Teams policies, SharePoint permissions, "
                "Azure AD groups, and service health tickets. No migration ownership."
            ),
        }],
        "projects": [],
        "resume_quality_score": 86,
    }

    _, result = score_m365(parsed)

    assert result["final_score"] <= 65
    assert result["label"] != "Strong Match"
    assert "generic_admin_without_migration" in result["recruiter_flags"]


def test_helpdesk_desktop_support_scores_low():
    parsed = {
        "full_name": "Support Analyst",
        "designation": "IT Helpdesk Engineer",
        "key_skills": ["Microsoft 365", "Windows", "Ticketing", "Desktop Support"],
        "total_experience_years": 8,
        "experience": [{
            "company_name": "Support Desk",
            "role": "Helpdesk Engineer",
            "description": "Handled service desk tickets, password resets, desktop support, printer support, and Windows troubleshooting.",
        }],
        "projects": [],
        "resume_quality_score": 82,
    }

    _, result = score_m365(parsed)

    assert result["final_score"] <= 42
    assert result["label"] == "Low Fit"
    assert "generic_support" in result["recruiter_flags"]


def test_azure_cloud_engineer_without_m365_migration_scores_low():
    parsed = {
        "full_name": "Azure Engineer",
        "designation": "Azure Cloud Engineer",
        "key_skills": ["Azure", "Terraform", "AKS", "VNet", "Virtual Machines"],
        "total_experience_years": 9,
        "experience": [{
            "company_name": "Cloud Infra",
            "role": "Azure Cloud Engineer",
            "description": "Built Azure infrastructure, Terraform modules, AKS clusters, VNets, virtual machines, and landing zones.",
        }],
        "projects": [],
        "resume_quality_score": 85,
    }

    _, result = score_m365(parsed)

    assert result["final_score"] <= 58
    assert result["label"] == "Low Fit"
    assert "azure_only" in result["recruiter_flags"]


def test_sharepoint_developer_without_migration_scores_low():
    parsed = {
        "full_name": "SharePoint Dev",
        "designation": "SharePoint Developer",
        "key_skills": ["SharePoint", "SPFx", "Power Apps", "Power Automate"],
        "total_experience_years": 8,
        "experience": [{
            "company_name": "Collab Apps",
            "role": "SharePoint Developer",
            "description": "Built SPFx webparts, Power Apps, Power Automate workflows, and SharePoint custom forms.",
        }],
        "projects": [],
        "resume_quality_score": 83,
    }

    _, result = score_m365(parsed)

    assert result["final_score"] <= 55
    assert result["label"] == "Low Fit"
    assert "sharepoint_dev_only" in result["recruiter_flags"]


def test_project_manager_without_hands_on_migration_scores_low():
    parsed = {
        "full_name": "Delivery PM",
        "designation": "Migration Project Manager",
        "key_skills": ["Project Management", "Scrum", "Stakeholder Management", "Status Reporting"],
        "total_experience_years": 10,
        "experience": [{
            "company_name": "PMO Services",
            "role": "Project Manager",
            "description": "Managed project governance, stakeholder status reporting, resource planning, and delivery timelines.",
        }],
        "projects": [],
        "resume_quality_score": 84,
    }

    _, result = score_m365(parsed)

    assert result["final_score"] <= 48
    assert result["label"] == "Low Fit"
    assert "project_manager_only" in result["recruiter_flags"]


def test_same_title_different_jd_creates_different_profile_hash_and_profile():
    admin_jd = """
    Microsoft 365 SME. Experience 8-10 years. Manage users, licenses, mailboxes,
    Teams administration, SharePoint permissions, Azure AD groups, service desk
    escalations, compliance settings, and day-to-day M365 platform support.
    """

    migration_profile = m365_profile()
    admin_profile = m365_profile(admin_jd, "Microsoft 365 SME")

    assert migration_profile["profile_jd_hash"] != admin_profile["profile_jd_hash"]
    assert migration_profile["role_family"] == "m365_migration_sme"
    assert admin_profile["core_skill_groups"] != migration_profile["core_skill_groups"]
