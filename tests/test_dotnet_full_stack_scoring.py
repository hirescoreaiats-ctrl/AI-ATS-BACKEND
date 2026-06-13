from backend.experience_engine import process_experience
from backend.jd_engine import normalize_jd_skills
from backend.services.experience_relevance import estimate_relevant_experience_v2
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.scoring_service import score_candidate


DOTNET_JD = """
Senior / Lead .NET Full Stack Engineer. Experience 8 Years to 12 Years.
Required Skills: Net Developer, Angular 7+, .Net Core and SQL.
Design, develop, and maintain full-stack applications using .NET Framework and .NET Core (C#),
Angular (7+), and SQL Server. Build and optimize RESTful APIs. Write SQL Server queries,
stored procedures, PL/SQL, SQL performance tuning and database optimization.
Implement authentication & authorization flows, including OAuth and Single Sign-On (SSO).
Use Redis distributed caching, Git, Agile/Scrum, CI/CD pipelines and Azure.
"""


DOTNET_NO_AUTH_JD = """
Senior .NET Full Stack Engineer. Experience 8 to 12 years.
Required Skills: .NET Core, C#, ASP.NET Core, Web API, Angular 7+, SQL Server, Git.
Responsibilities: develop RESTful APIs, Angular front-end applications, SQL queries and stored procedures.
"""


def dotnet_profile(jd_text=DOTNET_JD):
    skills = normalize_jd_skills([], jd_text)
    return build_jd_profile(
        jd_text,
        {"role": "Senior / Lead .NET Full Stack Engineer", "experience_required": "8-12 Years"},
        skills,
    )


def score_dotnet(parsed, jd_text=DOTNET_JD):
    profile = dotnet_profile(jd_text)
    resume_text = " ".join(
        [
            str(parsed.get("designation") or ""),
            " ".join(str(skill) for skill in parsed.get("key_skills") or []),
            " ".join(str(exp.get("description") or "") for exp in parsed.get("experience") or []),
        ]
    )
    parsed.update(estimate_relevant_experience_v2(parsed, resume_text, profile))
    result = score_candidate(parsed, jd_text, profile["must_have_skills"], {"role": profile["role_title"]}, resume_text, jd_profile=profile)
    return profile, result


def test_dotnet_role_family_and_jd_profile_groups_are_extracted():
    profile = dotnet_profile()

    assert profile["role_family"] == "dotnet_full_stack"
    assert "backend" in profile["core_skill_groups"]
    assert "frontend" in profile["core_skill_groups"]
    assert "database" in profile["core_skill_groups"]
    assert "auth_security" in profile["core_skill_groups"]
    assert ".NET Core" in profile["backend_groups"]["backend"]
    assert "Angular" in profile["frontend_groups"]["frontend"]
    assert "SQL Server" in profile["database_groups"]["database"]


def test_strong_dotnet_twelve_year_candidate_scores_above_85_no_backend_gap():
    parsed = {
        "full_name": "Manne Yadagiri",
        "designation": "Senior Software Engineer",
        "key_skills": [
            "C#.net", "ASP.NET MVC", "ASP.NET Core", "Web API", "RESTful APIs",
            "SQL Server", "Angular", "TypeScript", "JavaScript", "Kendo UI",
            "Telerik", "Azure", "Azure CI/CD Pipelines", "GitHub", "Agile",
        ],
        "total_experience_years": 12.14,
        "role_relevance_score": 92,
        "experience": [{
            "company_name": "Covantech Pvt Ltd",
            "role": "Senior Software Engineer",
            "start_date": "Jan 2014",
            "end_date": "Feb 2026",
            "description": "Designed and developed .NET Core, ASP.NET MVC, ASP.NET Core Web API, C#, RESTful APIs, Angular, SQL Server stored procedures, Azure CI/CD pipelines, GitHub and Agile enterprise applications.",
        }],
        "resume_quality_score": 92,
    }

    _profile, result = score_dotnet(parsed)

    assert result["final_score"] >= 85
    assert "Backend" not in result["missing_skills"]
    assert "backend" in result["matched_core_skill_groups"]
    assert result["jd_role_family"] == "dotnet_full_stack"
    assert ".NET Core" in result["matched_skills"] or "ASP.NET Core" in result["matched_skills"]


def test_dotnet_ten_plus_year_candidate_with_full_coverage_not_stuck_at_68():
    parsed = {
        "full_name": "Sathiendran T",
        "designation": "Senior Software Engineer",
        "key_skills": [".NET Core", "Angular", "SQL Server", "Microservices", "REST API", "C#", "AngularJS", "HTML", "CSS", "JavaScript", "TypeScript", "ASP.NET MVC", "Entity Framework", "Docker", "Git"],
        "total_experience_years": 11.84,
        "role_relevance_score": 88,
        "experience": [
            {
                "company_name": "DigiSME Software Pvt Ltd",
                "role": "Senior Software Engineer",
                "start_date": "Jan 2021",
                "end_date": "Feb 2026",
                "description": "Designed and developed .NET Core microservices, REST API, Angular, SQL Server stored procedures, Entity Framework, Git, Docker and SQL optimization.",
            },
            {
                "company_name": "Rinsoft Pvt Ltd",
                "role": "Software Engineer",
                "start_date": "Mar 2014",
                "end_date": "Dec 2020",
                "description": "Developed ASP.NET MVC, C#, AngularJS, JavaScript, SQL Server queries and REST APIs for enterprise applications.",
            },
        ],
        "resume_quality_score": 90,
    }

    _profile, result = score_dotnet(parsed)

    assert result["mandatory_skill_coverage"] >= 90
    assert result["final_score"] >= 80
    assert "Backend" not in result["missing_skills"]


def test_dotnet_hcltech_candidate_credits_relevant_years_and_rejects_client_company():
    company_result = process_experience([
        {"company_name": "CBA", "role": "Lead Engineer", "start_date": "Jan 2025", "end_date": "Present"},
        {"company_name": "HCLTech || Chennai", "role": "Lead Engineer", "start_date": "Jan 2023", "end_date": "Present"},
    ])
    assert company_result["last_company_name"] == "HCLTech"

    parsed = {
        "full_name": "Shreemanta Nanda",
        "designation": "Lead Engineer",
        "key_skills": ["C#", "JavaScript", "TypeScript", "HTML", "CSS", "React", "Angular", "GitHub", "Jira", "Agile", "Azure", "Bootstrap", "MVC", "REST API", "SQL Server", ".NET Core", "CI/CD"],
        "total_experience_years": 9.64,
        "role_relevance_score": 70,
        "experience": [
            {
                "company_name": "HCLTech",
                "role": "Lead Engineer",
                "start_date": "Jan 2023",
                "end_date": "Present",
                "description": "Led .NET Core, C#, Angular, REST API, SQL Server, Azure CI/CD, Git and Agile delivery for enterprise applications.",
            },
            {
                "company_name": "Previous Technologies Pvt Ltd",
                "role": "Software Engineer",
                "start_date": "Jul 2016",
                "end_date": "Dec 2022",
                "description": "Built ASP.NET MVC, Web API, C#, JavaScript, SQL Server and Angular modules.",
            },
        ],
        "resume_quality_score": 88,
    }

    _profile, result = score_dotnet(parsed)

    assert parsed["relevant_experience_years"] >= 8
    assert result["final_score"] >= 80


def test_dotnet_no_auth_jd_does_not_mark_api_auth_missing():
    parsed = {
        "full_name": "GJD Surrendra Sagar",
        "designation": "Sr. Software Engineer",
        "key_skills": ["ASP.NET", "C#.net", "MVC", "ASP.NET Core", "ASP .NET Web API", "ASP .NET Web API Core", "ADO.NET", "LINQ", "Entity Framework", "JavaScript", "Angular", "Git", "SQL Server", "Azure"],
        "total_experience_years": 8.97,
        "role_relevance_score": 82,
        "experience": [{
            "company_name": "Prutech Solutions India Pvt Ltd",
            "role": "Sr. Software Engineer",
            "start_date": "Jan 2017",
            "end_date": "Present",
            "description": "Developed ASP.NET Core, ASP.NET MVC, ASP.NET Web API Core, C#, ADO.NET, LINQ, Entity Framework, SQL Server, Angular 14, Git and Azure applications.",
        }],
        "resume_quality_score": 86,
    }

    profile, result = score_dotnet(parsed, DOTNET_NO_AUTH_JD)

    assert "api_auth" not in profile["core_skill_groups"]
    assert "auth_security" not in profile["core_skill_groups"]
    assert "Api Auth" not in result["missing_skills"]
    assert "Backend" not in result["missing_skills"]
    assert result["final_score"] >= 80
