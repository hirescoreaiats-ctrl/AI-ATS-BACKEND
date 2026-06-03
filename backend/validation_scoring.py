import re
from datetime import datetime
from dateutil import parser

from backend.skill_normalizer import normalize_skills, match_skills
from backend.seniority_engine import calculate_seniority_penalty


# ---------------- VALIDATION ----------------

def validate_email(email):

    if not email:
        return None

    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"

    return email if re.match(pattern, email) else None


def validate_phone(phone):

    if not phone:
        return None

    digits = re.sub(r"\D", "", phone)

    if len(digits) >= 10:
        return digits[-10:]

    return None


# ---------------- DATE PARSING ----------------

def parse_date(date_str):

    if not date_str:
        return None

    date_str = str(date_str).strip().lower()

    if date_str in ["present", "current", "till date"]:
        return datetime.now()

    try:
        return parser.parse(date_str, fuzzy=True)

    except:
        return None


# ---------------- EXPERIENCE CALCULATION ----------------

def calculate_experience(experience_list, required_keywords):

    total_years = 0
    relevant_years = 0

    if not experience_list:
        return 0, 0

    for job in experience_list:

        if not isinstance(job, dict):
            continue

        start = parse_date(job.get("start_date"))
        end = parse_date(job.get("end_date"))

        if not start:
            continue

        if not end:
            end = datetime.now()

        if end < start:
            continue

        years = (end - start).days / 365

        total_years += years

        text = (
            (job.get("role") or "") +
            " " +
            (job.get("description") or "")
        ).lower()

        if any(keyword.lower() in text for keyword in required_keywords):
            relevant_years += years

    return round(total_years, 2), round(relevant_years, 2)


# ---------------- FINAL SCORING ----------------

def calculate_final_score(parsed_resume, jd_skills, jd_data):

    # normalize skills
    candidate_skills = normalize_skills(parsed_resume.get("key_skills", []))
    jd_required = normalize_skills(jd_skills)

    # ---------------- SKILL MATCHING ----------------

    matched_skills, missing_skills = match_skills(
        candidate_skills,
        jd_required
    )

    total_required = len(jd_required)

    # -------- Skill Score (40%) --------

    if total_required > 0:
        skill_score = round((len(matched_skills) / total_required) * 40)
    else:
        skill_score = 0

    # -------- Skill Match Percent --------

    if total_required > 0:
        skill_match_percent = round(
            (len(matched_skills) / total_required) * 100,
            2
        )
    else:
        skill_match_percent = 0

    # -------- Experience Score (30%) --------

    min_required_exp = jd_data.get("min_experience_years", 0)

    relevant_exp = parsed_resume.get("relevant_experience_years", 0)

    if min_required_exp == 0:

        if relevant_exp >= 3:
            experience_score = 30

        elif relevant_exp >= 1:
            experience_score = 20

        elif relevant_exp > 0:
            experience_score = 10

        else:
            experience_score = 0

    else:

        if relevant_exp >= min_required_exp:
            experience_score = 30

        elif relevant_exp >= min_required_exp * 0.5:
            experience_score = 15

        else:
            experience_score = 0

    # -------- Semantic Score (25%) --------

    semantic_score = parsed_resume.get("semantic_score", 0)

    semantic_weight = int(semantic_score * 25)

    # -------- Role Similarity (15%) --------

    role_similarity = parsed_resume.get("role_similarity", 0)

    role_weight = int(role_similarity * 15)

    # -------- Education Score (10%) --------

    education_required = (jd_data.get("education") or "").lower()
    education_list = parsed_resume.get("education") or []

    if isinstance(education_list, str):
        education_list = [{"degree": education_list}]

    candidate_education = " ".join(
        str(item.get("degree", "")) if isinstance(item, dict) else str(item)
        for item in education_list
    ).lower()

    education_score = 0

    if education_required:

        if "bachelor" in education_required:

            if any(word in candidate_education for word in ["bachelor", "b.tech", "btech"]):
                education_score = 10

        elif "master" in education_required:

            if any(word in candidate_education for word in ["master", "m.tech", "mtech"]):
                education_score = 10

    # -------- Seniority Penalty --------

    jd_role = jd_data.get("role", "")

    resume_role = parsed_resume.get("designation", "")

    seniority_penalty = calculate_seniority_penalty(
        jd_role,
        resume_role
    )

    # -------- Final Score --------

    final_score = (
        skill_score
        + experience_score
        + semantic_weight
        + role_weight
        + education_score
        - seniority_penalty
    )

    return {

        "final_score": final_score,

        "skill_score": skill_score,

        "experience_score": experience_score,

        "semantic_score": semantic_score,

        "semantic_weight": semantic_weight,

        "role_similarity": role_similarity,

        "role_weight": role_weight,

        "education_score": education_score,

        "seniority_penalty": seniority_penalty,

        "matched_skills": matched_skills,

        "missing_skills": missing_skills,

        "skill_match_percent": skill_match_percent
    }