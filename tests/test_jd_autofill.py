from backend.routers.job import _jd_autofill_payload


def test_jd_autofill_rejects_requirement_text_as_title_and_splits_fields():
    jd_text = """
    JOB TITLE
    Minimum 3 years of professional experience

    COMPANY NAME
    Infometry

    DEPARTMENT
    s.

    JOB LOCATION
    Noida / Gurugram / Hybrid

    WORK MODE
    Hybrid

    JOB TYPE
    Full Time

    EXPERIENCE REQUIRED
    Required: 3+ Years | Employment Type: Full-time | Location: Noida/Gurugram/Hybrid

    SALARY RANGE
    8-12 LPA

    Job Description
    Responsibilities, requirements, skills, qualifications, and screening context.
    """

    fields = _jd_autofill_payload(jd_text)

    assert fields["job_title"] == ""
    assert fields["department"] != "s."
    assert fields["location"] == "Noida / Gurugram"
    assert fields["work_mode"] == "Hybrid"
    assert fields["job_type"] == "Full Time"
    assert fields["experience_required"] == "3+ Years"
    assert fields["salary_range"] == "8-12 LPA"
