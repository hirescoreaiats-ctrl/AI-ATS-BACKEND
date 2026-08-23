import json
from pathlib import Path

import pytest

from backend.services.jd_profile_engine import build_jd_profile


CASES = json.loads((Path(__file__).parent / "golden" / "role_family_cases.data").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_golden_jd_role_family_does_not_regress(case):
    profile = build_jd_profile(
        f"{case['title']}. {case['jd']}",
        {"role": case["title"], "job_title": case["title"]},
    )

    assert profile["role_family"] == case["role_family"]
    assert profile["role_family_confidence"] >= 70
    assert profile["core_skill_groups"]
