import os
import logging
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an AI hiring analyst.
Generate a concise recruiter explanation.
Maximum 4 sentences.
Highlight strengths and gaps.
Be objective and professional.
"""


def generate_candidate_explanation(candidate, jd_text):
    if not client:
        matched = candidate.get("matched_skills") or "No direct skill evidence"
        missing = candidate.get("missing_skills") or "No major gaps listed"
        score = candidate.get("final_score") or 0
        projects = candidate.get("projects") or []
        project_text = ""
        if isinstance(projects, list) and projects:
            project_text = "\n\nProjects:\n" + "\n".join(
                f"- {(p.get('name') or 'Project')}: {(p.get('description') or '')[:180]}"
                if isinstance(p, dict) else f"- {str(p)[:180]}"
                for p in projects[:4]
            )
        return (
            f"Summary: Candidate scored {score}/100 for this role based on resume evidence.\n\n"
            f"Strengths:\n- Matched skills: {matched}\n\n"
            f"{project_text}\n\n"
            f"Gaps:\n- {missing}\n\n"
            "Verdict: Consider if the matched skills align with the recruiter's priority areas."
        )

    prompt = f"""
    You are a strict hiring evaluator.

    Job Description:
    {jd_text[:1500]}

    Candidate Resume:
    {candidate.get("resume_text")}

    Extracted Projects:
    {candidate.get("projects")}

    Instructions:
    - Be direct and factual
    - No praise, no fluff
    - Identify real projects/work from resume
    - Mention specific projects if present
    - Do NOT give generic statements
    - Focus on actual work done

    Format:

    Summary:
    1-2 lines: fit or not

    Strengths:
    - Mention actual projects or work (if found)
    - Mention tools used in those projects

    Gaps:
    - Missing skills or missing project experience

    Verdict:
    - Strong Hire / Consider / Reject
    - One-line reason
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert hiring analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )

        return response.choices[0].message.content.strip()

    except Exception:
        logger.exception("AI explanation generation failed")
        return "AI explanation not available."
