import re

SENIORITY_WEIGHTS = {
    "intern": -2,
    "trainee": -2,
    "junior": -1,
    "associate": -1,
    "senior": 1,
    "lead": 2,
    "manager": 3,
    "director": 4,
    "head": 4,
    "vp": 5,
    "principal": 3
}


def infer_seniority_score(title: str):
    if not title:
        return 0

    title = title.lower()
    score = 0

    for word, weight in SENIORITY_WEIGHTS.items():
        if re.search(rf"\b{word}\b", title):
            score += weight

    return score


def calculate_seniority_penalty(jd_role, resume_role):
    jd_score = infer_seniority_score(jd_role)
    resume_score = infer_seniority_score(resume_role)

    # Resume lower level than JD → penalty
    if resume_score < jd_score:
        difference = jd_score - resume_score
        return difference * 3  # 3 points per level difference

    return 0