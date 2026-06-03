from __future__ import annotations

import json

from backend.models import AuditLog, CandidateActivity


def write_audit_log(
    db,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor_user_id: str | None = None,
    organization_id: str | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    log = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        metadata_json=json.dumps(metadata or {}),
        ip_address=ip_address,
    )
    db.add(log)
    return log


def write_candidate_activity(
    db,
    *,
    candidate_id: str,
    activity_type: str,
    title: str,
    job_id: str | None = None,
    actor_user_id: str | None = None,
    body: str | None = None,
) -> CandidateActivity:
    activity = CandidateActivity(
        candidate_id=candidate_id,
        job_id=job_id,
        actor_user_id=actor_user_id,
        activity_type=activity_type,
        title=title,
        body=body,
    )
    db.add(activity)
    return activity
