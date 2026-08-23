from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CapabilityRule:
    canonical: str
    aliases: tuple[str, ...]
    pattern: re.Pattern
    requires_embedded_context: bool = False


EMBEDDED_CONTEXT_RE = re.compile(
    r"\b(?:firmware|embedded|rtos|bare[-\s]?metal|bsp|bootloaders?|device\s+drivers?|"
    r"boards?|pcbs?|peripherals?|mcu|microcontrollers?|real[-\s]?time|jtag|gpio|"
    r"sistemas?\s+embarcados?|microcontroladores?|placas?\s+de\s+circuito)\b",
    re.I,
)


def _rule(canonical: str, aliases: Iterable[str], pattern: str, *, context: bool = False) -> CapabilityRule:
    return CapabilityRule(canonical, tuple(aliases), re.compile(pattern, re.I), context)


# These are capabilities rather than a flat keyword synonym table.  A rule may
# require embedded context so adjacent web/cloud uses of ARM, Linux, testing,
# or automation do not leak into the firmware family.
CAPABILITY_RULES = (
    _rule("C", ("c programming", "c language"), r"(?<![A-Za-z0-9+#.])C(?![A-Za-z0-9+#.])|\bC\s+programming\b"),
    _rule(
        "Microcontrollers",
        ("mcu", "microcontroller", "stm32", "esp32", "avr", "pic", "nxp", "freescale", "silabs", "atmel", "arm cortex-m"),
        r"\b(?:microcontrollers?|mcus?|stm32\w*|esp32\w*|avr\w*|pic(?:18|24|32)?\w*|"
        r"nxp(?:\s+(?:mcu|microcontroller|processor))?|freescale|silicon\s+labs?|silabs|atmel|"
        r"arm\s+cortex[-\s]?m\d*|cortex[-\s]?m\d*|microcontroladores?)\b",
        context=True,
    ),
    _rule(
        "Embedded Firmware",
        ("firmware", "embedded software", "device firmware", "mcu firmware", "bsp", "bootloader", "device drivers"),
        r"\b(?:embedded\s+(?:firmware|software|systems?)|device\s+firmware|mcu\s+firmware|firmware|"
        r"bare[-\s]?metal|rtos|free\s*rtos|bsp|board\s+support\s+package|bootloaders?|device\s+drivers?)\b",
    ),
    _rule(
        "Embedded Hardware",
        ("embedded hw", "board bring-up", "pcb", "hardware drivers", "board-level debugging"),
        r"\b(?:embedded\s+(?:hardware|hw)|board[-\s]?level|board\s+bring[-\s]?up|pcbs?|"
        r"schematic(?:s|\s+development)?|circuit\s+design|board\s+design|control\s+electronics|"
        r"hardware\s+(?:drivers?|validation|debugging)|custom\s+boards?)\b|"
        r"\b(?:stm32\w*|esp32\w*|microcontrollers?|mcus?)\b.{0,100}\b(?:boards?|peripherals?|firmware|drivers?)\b|"
        r"\b(?:boards?|peripherals?|firmware|drivers?)\b.{0,100}\b(?:stm32\w*|esp32\w*|microcontrollers?|mcus?)\b",
        context=True,
    ),
    _rule(
        "Hardware/Software Integration",
        ("hw/fw integration", "system integration", "board integration", "peripheral interfacing"),
        r"\b(?:hardware\s*/\s*(?:software|firmware)|hw\s*/\s*fw|hardware[-\s]+software|"
        r"hardware[-\s]+firmware|system\s+integration|board\s+bring[-\s]?up|peripheral\s+interfac(?:e|ing)|"
        r"embedded\s+linux\s+drivers?|hardware\s+test\s+integration)\b|"
        r"\bfirmware\b.{0,100}\b(?:boards?|hardware|peripherals?|drivers?)\b|"
        r"\b(?:boards?|hardware|peripherals?|drivers?)\b.{0,100}\bfirmware\b",
        context=True,
    ),
    _rule(
        "Debugging",
        ("troubleshooting", "root cause analysis", "bug fixing", "triage"),
        r"\b(?:debug(?:ged|ging)?|troubleshoot(?:ed|ing)?|root[-\s]?cause\s+analysis|triage|"
        r"bug\s+fix(?:es|ing)?|defect\s+(?:resolution|fixing)|failure\s+analysis|board\s+bring[-\s]?up)\b",
    ),
    _rule(
        "Peripheral Interfaces",
        ("i2c", "spi", "uart", "usb", "adc", "dac", "can", "lin", "jtag", "gpio", "sensors"),
        r"\b(?:i2c|i²c|spi|uart|usb|adc|dac|can(?:\s+bus)?|lin(?:\s+bus)?|ethernet|jtag|gpio|sensors?|peripherals?)\b",
        context=True,
    ),
    _rule(
        "RF Systems",
        ("radio systems", "rf testing", "rf transceiver", "hf", "vhf", "wireless communication"),
        r"\b(?:rf(?:[-\s]?over[-\s]?fiber)?|radio\s+systems?|rf\s+(?:systems?|testing|transceivers?)|"
        r"hf|vhf|broadband\s+radios?|wireless\s+communications?|telecommunications?\s+hardware|"
        r"optical\s+communications?)\b",
    ),
    _rule(
        "Manufacturing Test",
        ("factory testing", "production testing", "test platforms", "diagnostic tools", "oem support", "odm support"),
        r"\b(?:manufacturing|factory|production)\s+(?:test(?:ing)?|qualification|support)|"
        r"\b(?:validation\s+scripts?|test\s+(?:suites?|platforms?|fixtures?)|diagnostic\s+(?:tools?|utilities)|"
        r"hardware\s+validation\s+infrastructure|oem\s*/?\s*odm\s+support)\b",
    ),
    _rule(
        "Continuation Engineering",
        ("legacy engineering", "lifecycle support", "refactoring", "existing product maintenance"),
        r"\b(?:continuation\s+engineering|legacy\s+(?:c\s+)?(?:code|firmware|systems?)|inherited\s+codebase|"
        r"old\s+build[-\s]?system\s+migration|maintain(?:ed|ing)?\s+(?:old|existing|legacy)\s+firmware|"
        r"defect\s+resolution|field\s+updates?|upgrade\s*/?\s*recovery|product\s+revisions?|"
        r"refactor(?:ed|ing)?|product\s+lifecycle\s+support)\b",
    ),
    _rule(
        "Electronic Schematics",
        ("schematic development", "circuit design", "pcb design", "board design", "electronics"),
        r"\b(?:schematic(?:s|\s+development)?|circuit\s+design|pcb\s+(?:design|development)|"
        r"board\s+(?:design|development)|electronic\s+product\s+design|eletr[oô]nica|"
        r"desenvolvimento\s+de\s+esquem[aá]tico|placas?\s+de\s+circuito\s+impresso)\b",
    ),
    _rule(
        "Laboratory Equipment",
        ("oscilloscope", "multimeter", "logic analyzer", "jtag debugger", "instrumentation"),
        r"\b(?:oscilloscopes?|oscilosc[oó]pios?|multimeters?|mult[ií]metros?|logic\s+analy[sz]ers?|"
        r"jtag\s+debuggers?|test\s+instrumentation|laboratory\s+equipment|lab\s+equipment|"
        r"data\s+acquisition|instrumentation)\b",
    ),
    _rule(
        "Software Engineering",
        ("software architecture", "design patterns", "code review", "clean code", "documentation"),
        r"\b(?:software\s+engineering|software\s+architecture|design\s+patterns?|abstraction|decoupling|"
        r"cohesion|uml|code\s+reviews?|clean\s+code|modular|maintainable\s+code)\b",
    ),
)


CANONICAL_ALIASES = {
    alias.lower(): rule.canonical
    for rule in CAPABILITY_RULES
    for alias in (rule.canonical, *rule.aliases)
}
CANONICAL_ALIASES.update({
    "firmware": "Embedded Firmware",
    "embedded software": "Embedded Firmware",
    "embedded systems": "Embedded Firmware",
    "laboratory equipment": "Laboratory Equipment",
    "electronic schematics": "Electronic Schematics",
})


def canonical_capability(value: str) -> str:
    return CANONICAL_ALIASES.get(str(value or "").strip().lower(), str(value or "").strip())


def _source_blocks(parsed: dict) -> list[tuple[str, str, dict]]:
    blocks = []
    for job in parsed.get("experience") or []:
        if isinstance(job, dict):
            blocks.append(("work_experience", " ".join(str(job.get(key) or "") for key in ("role", "description")), {
                "role": job.get("role") or "",
                "company": job.get("company_name") or job.get("company") or "",
                "start_date": job.get("start_date"),
                "end_date": job.get("end_date"),
            }))
    for project in parsed.get("projects") or []:
        if isinstance(project, dict):
            blocks.append(("project", " ".join(str(project.get(key) or "") for key in ("name", "title", "description", "summary")), {
                "project": project.get("name") or project.get("title") or "",
            }))
    blocks.append(("skills_section", " ".join(str(item) for item in parsed.get("key_skills") or []), {}))
    return blocks


def _snippet(text: str, match: re.Match) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[max(0, match.start() - 90): min(len(clean), match.end() + 170)].strip(" ,.;:-")[:320]


def capability_evidence(required: str, parsed: dict | None, resume_text: str = "", role_family: str = "other") -> dict | None:
    """Return the strongest explainable evidence for a canonical capability.

    The result keeps the original evidence alongside the canonical capability.
    Skills-only and unsegmented evidence intentionally resolve to VERIFY.
    """
    canonical = canonical_capability(required)
    rule = next((item for item in CAPABILITY_RULES if item.canonical == canonical), None)
    if not rule:
        return None
    if rule.requires_embedded_context and role_family != "embedded_firmware":
        return None

    parsed = parsed or {}
    candidates = []
    for source, text, metadata in _source_blocks(parsed):
        match = rule.pattern.search(text or "")
        if not match:
            continue
        evidence_text = _snippet(text, match)
        context_ok = not rule.requires_embedded_context or bool(EMBEDDED_CONTEXT_RE.search(text or ""))
        if not context_ok:
            continue
        if source == "work_experience":
            action = bool(re.search(
                r"\b(?:developed|designed|implemented|built|integrated|debugged|tested|validated|"
                r"maintained|refactored|troubleshot|created|supported|engineered|programmed|worked\s+on)\b",
                text,
                re.I,
            ))
            level, weight = ("professional_strong", 1.0) if action else ("professional_weak", 0.78)
            candidates.append((5 if action else 4, source, level, weight, evidence_text, metadata))
        elif source == "project":
            action = bool(re.search(r"\b(?:developed|designed|implemented|built|integrated|debugged|tested|created)\b", text, re.I))
            level, weight = ("project_strong", 0.76) if action else ("project_weak", 0.52)
            candidates.append((3 if action else 2, source, level, weight, evidence_text, metadata))
        else:
            candidates.append((1, source, "skills_section_only", 0.36, evidence_text, metadata))

    if not candidates:
        match = rule.pattern.search(resume_text or "")
        if match and (not rule.requires_embedded_context or EMBEDDED_CONTEXT_RE.search(resume_text or "")):
            candidates.append((1, "resume_text", "contextual_support", 0.30, _snippet(resume_text, match), {}))
    if not candidates:
        return None

    _, source, level, weight, original, metadata = max(candidates, key=lambda item: item[0])
    verify = level in {"skills_section_only", "contextual_support"}
    return {
        "skill": required,
        "canonical_capability": canonical,
        "original_evidence": original,
        "evidence_text": original,
        "status": "verify" if verify else "matched",
        "evidence_state": "VERIFY" if verify else "MATCHED",
        "evidence_level": level,
        "depth": "skills_section_evidence" if verify else ("project_evidence" if source == "project" else "work_experience_evidence"),
        "source": source,
        "weight": weight,
        "employer_name_only": False,
        "inference": canonical != required,
        "role": metadata.get("role") or None,
        "company": metadata.get("company") or None,
        "project": metadata.get("project") or None,
        "start_date": metadata.get("start_date"),
        "end_date": metadata.get("end_date"),
        "evidence_recency": "recent" if re.search(r"\b(?:202[2-9]|present|current)\b", " ".join(str(metadata.get(key) or "") for key in ("start_date", "end_date")), re.I) else "historical_or_unknown",
        "evidence_type": "direct" if not verify else "needs_verification",
    }
