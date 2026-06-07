from __future__ import annotations

import re
from dataclasses import dataclass


RESUME_POSITIVE_PATTERNS = [
    r"\b(work|professional|employment)\s+experience\b",
    r"\b(education|academic qualification|certifications?)\b",
    r"\b(technical skills|key skills|skills|tools|technologies)\b",
    r"\b(projects?|portfolio projects?|academic projects?)\b",
    r"\b(linkedin|github|portfolio)\b",
    r"\b(?:data|business|bi|mis|software|salesforce|python|sql|excel|power\s*bi|tableau)\b",
]

NON_RESUME_PATTERNS = [
    r"\bjob\s+description\b",
    r"\bkey\s+(?:duties|responsibilities)\b",
    r"\broles?\s+and\s+responsibilities\b",
    r"\bminimum\s+\d+\s*\+?\s*(?:years?|yrs?)\s+of\s+professional\s+experience\b",
    r"\b(required|mandatory)\s+skills?\b",
    r"\bhow\s+to\s+apply\b",
    r"\bselection\s+process\b",
    r"\bsalary\s+range\b",
    r"\bcompany\s+name\b",
    r"\bdepartment\b",
    r"\bhiring\s+manager\b",
    r"\bapplication\s+deadline\b",
    r"\bpreferred\s+full\s+name\b",
    r"\bposition\s+applied\s+for\b",
    r"\bapplication\s+form\b",
]

STRONG_NON_RESUME_PHRASES = [
    "job title",
    "job type",
    "work mode",
    "experience required",
    "apply here",
    "external apply url",
]


@dataclass(frozen=True)
class DocumentClassification:
    is_resume: bool
    label: str
    reason: str
    positive_signals: int
    negative_signals: int


def classify_resume_document(text: str, filename: str = "") -> DocumentClassification:
    """Reject obvious JD/application-form uploads before they become candidates."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    lower = normalized.lower()
    if not normalized:
        return DocumentClassification(True, "unknown", "No readable text available for pre-classification.", 0, 0)

    positive = sum(1 for pattern in RESUME_POSITIVE_PATTERNS if re.search(pattern, normalized, re.I))
    negative = sum(1 for pattern in NON_RESUME_PATTERNS if re.search(pattern, normalized, re.I))
    strong_negative = sum(1 for phrase in STRONG_NON_RESUME_PHRASES if phrase in lower)
    word_count = len(re.findall(r"\w+", normalized))

    has_candidate_contact = bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", normalized)) or bool(
        re.search(r"(?:\+?\d[\d\s().-]{8,}\d)", normalized)
    )
    has_resume_structure = positive >= 3 and (has_candidate_contact or re.search(r"\bexperience\b.*\beducation\b|\beducation\b.*\bexperience\b", lower))

    if negative >= 3 and strong_negative >= 2 and not has_resume_structure:
        return DocumentClassification(False, "non_resume", "Document looks like a JD/application form, not a candidate resume.", positive, negative)
    if negative >= positive + 3 and not has_candidate_contact:
        return DocumentClassification(False, "non_resume", "Document has strong job-description signals and no candidate contact evidence.", positive, negative)
    if word_count < 45 and negative >= 2 and not has_candidate_contact:
        return DocumentClassification(False, "non_resume", "Document is too short and looks like job metadata.", positive, negative)

    return DocumentClassification(True, "resume_or_unknown", "Resume pre-classification passed.", positive, negative)
