async function loadExplanationPage(options = {}) {
    const params = new URLSearchParams(window.location.search);
    const resumeId = params.get("resume_id");
    const forceFromUrl = params.get("force") === "true";
    const forceRefresh = options.forceRefresh === true || forceFromUrl;
    const loader = document.getElementById("loadingScreen");
    const box = document.getElementById("explanationBox");

    if (!resumeId) {
        showError(loader, "Resume ID missing. Open this report from a candidate result row.");
        return;
    }

    try {
        const cacheKey = reportCacheKey(resumeId);
        setLoadingState(loader, box, forceRefresh ? "Regenerating AI report" : "Building candidate report");

        if (!forceRefresh) {
            const cached = readCachedReport(cacheKey);
            if (cached) {
                showReport(box, loader, cached.explanationData, cached.candidateData, "Saved report");
                return;
            }
        }

        let explanationUrl = `${API}/ai-explanation/${encodeURIComponent(resumeId)}`;
        if (forceRefresh) {
            explanationUrl += "?force=true";
        }

        const [explanationResult, candidateResult] = await Promise.allSettled([
            fetch(explanationUrl).then(parseJsonResponse),
            fetch(`${API}/candidate/track/${encodeURIComponent(resumeId)}`).then(parseJsonResponse),
        ]);

        if (explanationResult.status !== "fulfilled" || !explanationResult.value.explanation) {
            throw new Error("No AI explanation found for this candidate.");
        }

        const explanationData = explanationResult.value;
        const candidateFromResponse = explanationData.candidate || {};
        const candidateFromTrack = candidateResult.status === "fulfilled" && !candidateResult.value.error
            ? candidateResult.value
            : {};
        const candidateData = mergeCandidateData(candidateFromResponse, candidateFromTrack);

        writeCachedReport(cacheKey, explanationData, candidateData);
        showReport(box, loader, explanationData, candidateData);

        if (forceFromUrl) {
            params.delete("force");
            const nextUrl = `${window.location.pathname}?${params.toString()}`;
            window.history.replaceState({}, document.title, nextUrl);
        }
    } catch (error) {
        showError(loader, error.message || "Error loading candidate analysis.");
    }
}

function showReport(box, loader, explanationData, candidateData, sourceLabel = "") {
    loader.style.display = "none";
    box.classList.remove("hidden");
    box.innerHTML = renderAnalysis(explanationData, candidateData, sourceLabel);
}

function setLoadingState(loader, box, title) {
    box.classList.add("hidden");
    loader.style.display = "grid";
    loader.innerHTML = `
        <div class="loader"></div>
        <h2>${escapeHtml(title)}</h2>
        <p>Reading saved AI evidence, project history, score signals, and screening gaps.</p>
    `;
}

function reportCacheKey(resumeId) {
    return `aiCandidateAnalysis:v4:${resumeId}`;
}

function mergeCandidateData(primary, secondary) {
    const merged = { ...(primary || {}) };
    Object.entries(secondary || {}).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
            merged[key] = value;
        }
    });
    return merged;
}

function readCachedReport(cacheKey) {
    try {
        const cached = JSON.parse(sessionStorage.getItem(cacheKey) || "null");
        if (!cached || !cached.savedAt) return null;

        const maxAgeMs = 30 * 60 * 1000;
        if (Date.now() - cached.savedAt > maxAgeMs) {
            sessionStorage.removeItem(cacheKey);
            return null;
        }

        return cached;
    } catch {
        return null;
    }
}

function writeCachedReport(cacheKey, explanationData, candidateData) {
    try {
        sessionStorage.setItem(cacheKey, JSON.stringify({
            savedAt: Date.now(),
            explanationData,
            candidateData,
        }));
    } catch {
        // Browser storage can be unavailable; the backend cache still protects AI generation.
    }
}

async function parseJsonResponse(response) {
    if (!response.ok) {
        throw new Error(await response.text());
    }
    return response.json();
}

function renderAnalysis(explanationData, candidate, sourceLabel = "") {
    const sections = parseExplanation(explanationData.explanation || "");
    const candidateFromResponse = explanationData.candidate || {};
    candidate = mergeCandidateData(candidateFromResponse, candidate || {});
    const positiveEvidenceText = [
        sections.summary,
        ...sections.strengths,
    ].join(" ");
    const evidenceText = [
        positiveEvidenceText,
        ...sections.gaps,
        sections.verdict,
        explanationData.explanation || "",
    ].join(" ");
    const directProjects = normalizeProjects(explanationData.projects);
    const missingSkills = uniqueItems([
        ...splitSkillText(candidate.missing_skills),
        ...extractMissingSkillNames(sections.gaps.join(" ")),
    ]);
    const projectSeed = sections.strengths.length ? sections.strengths : [sections.summary];
    const projects = directProjects.length ? directProjects : projectsFromEvidence(projectSeed);
    const matchedSkills = uniqueItems([
        ...splitSkillText(candidate.matched_skills),
        ...splitSkillText(candidate.key_skills),
        ...extractTechnologies(positiveEvidenceText),
    ]).filter(skill => !hasSkillOverlap(skill, missingSkills));
    const storedScore = firstPositive(
        toNumber(candidate.final_score),
        toNumber(candidate.score),
        toNumber(candidate.skill_match_percent),
        extractScore(evidenceText)
    );
    const estimatedScore = estimateScoreFromEvidence(matchedSkills, missingSkills, projects);
    const score = Number.isFinite(storedScore) ? storedScore : estimatedScore;
    const confidence = firstFinite(toNumber(candidate.confidence_score), score);
    const hasScore = Number.isFinite(score);
    const isEstimatedScore = !Number.isFinite(storedScore) && hasScore;
    const verdictClass = !hasScore ? "is-review" : score >= 70 ? "is-strong" : score >= 50 ? "is-review" : "is-low";
    const verdictLabel = !hasScore ? "Review needed" : score >= 70 ? "Strong match" : score >= 50 ? "Needs review" : "Low match";
    const candidateName = candidate.name || "Candidate";
    const roleLine = [candidate.designation, candidate.job_title].filter(Boolean).join(" for ");
    const cacheText = sourceLabel || (explanationData.cached ? "Saved report" : "Generated now");
    const generatedText = formatGeneratedTime(explanationData.generated_at || candidate.explanation_generated_at || candidate.created_at);
    const scorePercent = hasScore ? Math.max(0, Math.min(100, Math.round(score))) : 55;
    const experienceValue = candidate.experience || extractExperience(evidenceText);
    const roleSignal = candidate.designation || extractRoleSignal(evidenceText);
    const toolsSignal = matchedSkills.slice(0, 3).join(", ") || "Skills need review";
    const followUpSignal = missingSkills.length ? `${missingSkills.length} items to verify` : "No major gaps listed";
    const executiveSummary = buildExecutiveSummary({
        candidate,
        sections,
        matchedSkills,
        missingSkills,
        projects,
        roleSignal,
        score,
        isEstimatedScore,
    });

    return `
        <article class="report-header">
            <div class="report-main">
                <div>
                    <div class="candidate-meta">
                        <span class="status-chip ${explanationData.cached || sourceLabel ? "is-generated" : "is-refresh"}">${escapeHtml(cacheText)}</span>
                        <span class="status-chip">${escapeHtml(candidate.status || "Review")}</span>
                        <span class="status-chip">${escapeHtml(verdictLabel)}</span>
                    </div>
                    <h2 class="candidate-title">${escapeHtml(candidateName)}</h2>
                    <p class="candidate-subtitle">${escapeHtml(roleLine || roleSignal || "Resume-to-job match analysis")}</p>
                    <p class="summary-copy">${escapeHtml(executiveSummary)}</p>
                </div>

                <aside class="score-box">
                    <div class="score-ring ${hasScore ? "" : "is-unscored"}" style="--score:${scorePercent}">
                        <div>
                            <strong>${hasScore ? Math.round(score) : "Review"}</strong>
                            <span>${hasScore ? (isEstimatedScore ? "Est. match" : "Match score") : "Score pending"}</span>
                        </div>
                    </div>
                    <p class="score-label">${escapeHtml(verdictLabel)}</p>
                </aside>
            </div>

            <div class="report-footer">
                ${footerItem("Generated", generatedText)}
                ${Number.isFinite(toNumber(experienceValue))
                    ? footerItem("Experience", formatExperience(experienceValue))
                    : footerItem("Project Evidence", `${projects.length || 0} ${projects.length === 1 ? "example" : "examples"}`)}
                ${footerItem(candidate.location ? "Location" : "Role Signal", candidate.location || roleSignal || "Role needs review")}
                ${footerItem(candidate.email || candidate.phone ? "Contact" : "Key Tools", candidate.email || candidate.phone || toolsSignal)}
            </div>
        </article>

        <section class="metric-strip">
            ${metricCard("Confidence", Number.isFinite(confidence) ? `${Math.round(confidence)}%` : "Needs review", "Model confidence in the screening evidence.")}
            ${metricCard("Matched skills", matchedSkills.length || 0, "Skills found in both resume and job context.")}
            ${metricCard("Follow-up", followUpSignal, "What the recruiter should verify next.")}
        </section>

        <section class="analysis-grid">
            <div class="analysis-column">
                <div class="analysis-card strength-card">
                    ${cardHeader("Strength Evidence", "Signals that support this candidate for the role.", `${sections.strengths.length} signals`)}
                    ${renderEvidenceList(sections.strengths, false, "No clear strengths were returned by the AI model.")}
                </div>

                <div class="analysis-card chart-card">
                    ${cardHeader("Screening Graph", "Visual balance of match signals and follow-up risk.", "Graph")}
                    ${renderSignalGraph(score, confidence, matchedSkills, missingSkills, projects)}
                </div>

                <div class="analysis-card skill-card">
                    ${cardHeader("Skill Coverage", "Matched and missing skills to guide recruiter follow-up.", "Skills")}
                    ${renderSkillCloud("Matched skills", matchedSkills, "No matched skills available.")}
                    ${renderSkillCloud("Missing skills", missingSkills, "No missing skills listed.")}
                </div>

                <div class="analysis-card gaps-card">
                    ${cardHeader("Gaps To Verify", "Weak areas or questions for screening.", `${sections.gaps.length} gaps`)}
                    ${renderEvidenceList(sections.gaps, true, "No specific gaps were returned by the AI model.")}
                </div>
            </div>

            <div class="analysis-column">
                <div class="analysis-card project-card-panel">
                    ${cardHeader("Project Evidence", "Concrete resume projects or work examples.", `${projects.length} found`)}
                    ${renderProjects(projects)}
                </div>

                <div class="analysis-card experience-card">
                    ${cardHeader("Experience Evidence", "Role, company, and work-history signals from the resume.", "Experience")}
                    ${renderExperienceEvidence(candidate, experienceValue, roleSignal, sections.strengths, projects, evidenceText)}
                </div>
            </div>

            <section class="verdict-card ${verdictClass}">
                ${cardHeader("Recruiter Verdict", "Decision support based on the saved AI evidence.", "Final")}
                <p class="verdict-text">${escapeHtml(sections.verdict || "No final verdict was returned.")}</p>
            </section>
        </section>
    `;
}

function footerItem(label, value) {
    return `
        <div class="footer-item">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
        </div>
    `;
}

function metricCard(label, value, detail) {
    return `
        <div class="metric-card">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
            <p>${escapeHtml(detail)}</p>
        </div>
    `;
}

function cardHeader(title, subtitle, count) {
    return `
        <div class="card-head">
            <div>
                <h2>${escapeHtml(title)}</h2>
                <p>${escapeHtml(subtitle)}</p>
            </div>
            <span class="count-badge">${escapeHtml(count)}</span>
        </div>
    `;
}

function buildExecutiveSummary({ candidate, sections, matchedSkills, missingSkills, projects, roleSignal, score, isEstimatedScore }) {
    const role = candidate.designation || candidate.job_title || roleSignal || "this role";
    const baseSummary = cleanSummarySentence(sections.summary);
    const scoreText = Number.isFinite(score)
        ? `${isEstimatedScore ? "estimated " : ""}match around ${Math.round(score)}%`
        : "score needs recruiter review";
    const tools = matchedSkills.slice(0, 5).join(", ");
    const projectText = projects.length
        ? `${projects.length} project/work evidence item${projects.length === 1 ? "" : "s"}`
        : "no clear project evidence";
    const strongestEvidence = compactSummaryFragment(
        sections.strengths[0] || projects[0]?.description || ""
    );
    const gapText = compactSummaryFragment(missingSkills.slice(0, 3).join(", ") || sections.gaps[0] || "");

    const parts = [
        `${candidate.name || "Candidate"} is mapped as ${role} with ${scoreText}.`,
    ];

    if (baseSummary) parts.push(baseSummary);
    if (tools) parts.push(`Relevant tools/signals: ${tools}.`);
    parts.push(`Resume evidence includes ${projectText}${strongestEvidence ? `, especially ${strongestEvidence}` : ""}.`);
    if (gapText) parts.push(`Verify gaps around ${gapText}.`);

    return parts.join(" ");
}

function cleanSummarySentence(value) {
    const text = cleanMarkdown(value)
        .replace(/\s+/g, " ")
        .replace(/^summary\s*:?\s*/i, "")
        .trim();
    if (!text || /not available/i.test(text)) return "";
    return text.endsWith(".") ? text : `${text}.`;
}

function compactSummaryFragment(value) {
    const text = String(value || "")
        .replace(/\s+/g, " ")
        .replace(/^[\s-]+/, "")
        .trim();
    if (!text) return "";
    const limit = 150;
    const clipped = text.length > limit ? `${text.slice(0, limit).trim()}...` : text;
    return clipped.replace(/\.$/, "");
}

function parseExplanation(rawText) {
    const text = String(rawText || "").replace(/\r/g, "\n").trim();
    const headingRegex = /(?:^|\n)[^\n]{0,24}\b(Summary|Strengths|Gaps|Verdict)\b\s*:?\s*/gi;
    const matches = [...text.matchAll(headingRegex)];
    const sections = {
        summary: "",
        strengths: [],
        gaps: [],
        verdict: "",
    };

    if (!matches.length) {
        sections.summary = firstUsefulSentence(text);
        sections.strengths = evidenceFromPlainText(text);
        sections.gaps = gapEvidenceFromPlainText(text);
        sections.verdict = verdictFromPlainText(text);
        return sections;
    }

    matches.forEach((match, index) => {
        const label = match[1].toLowerCase();
        const start = match.index + match[0].length;
        const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
        const content = cleanMarkdown(text.slice(start, end));

        if (label === "summary") sections.summary = content;
        if (label === "strengths") sections.strengths = toListItems(content);
        if (label === "gaps") sections.gaps = toListItems(content);
        if (label === "verdict") sections.verdict = content;
    });

    if (!sections.summary) {
        sections.summary = firstUsefulSentence(text.slice(0, matches[0].index)) || firstUsefulSentence(text);
    }

    if (!sections.strengths.length) {
        sections.strengths = evidenceFromPlainText(text);
    }

    if (!sections.gaps.length) {
        sections.gaps = gapEvidenceFromPlainText(text);
    }

    if (!sections.verdict) {
        sections.verdict = verdictFromPlainText(text);
    }

    return sections;
}

function firstUsefulSentence(value) {
    const cleaned = cleanMarkdown(value);
    const lines = cleaned.split(/\n+/).map(line => line.trim()).filter(Boolean);
    const candidate = lines.find(line => !/^(summary|strengths|gaps|verdict)$/i.test(line)) || cleaned;
    return candidate.replace(/^summary\s*:?\s*/i, "").trim();
}

function evidenceFromPlainText(value) {
    return toListItems(value)
        .filter(item => !/^(summary|gaps|verdict)\b/i.test(item))
        .filter(item => /\b(analyz|automat|built|develop|created|dashboard|skill|experience|project|power bi|excel|python|sql|reduc|improv|track|process|visuali)/i.test(item))
        .slice(0, 6);
}

function gapEvidenceFromPlainText(value) {
    return toListItems(value)
        .filter(item => /\b(no explicit|limited|lacking|lack|missing|gap|weak|preferred|not mention|not listed|verify)/i.test(item))
        .slice(0, 5);
}

function verdictFromPlainText(value) {
    const cleaned = cleanMarkdown(value);
    const verdictMatch = cleaned.match(/\b(?:verdict|consider|shortlist|reject|review)\b[^.\n]*(?:\.[^\n]*)?/i);
    return verdictMatch ? verdictMatch[0].trim() : "";
}

function cleanMarkdown(value) {
    return String(value || "")
        .replace(/\*\*/g, "")
        .replace(/`/g, "")
        .replace(/^[-*\s]+$/gm, "")
        .replace(/[ \t]+\n/g, "\n")
        .trim();
}

function toListItems(value) {
    const cleaned = cleanMarkdown(value);
    if (!cleaned) return [];

    let items = cleaned
        .split(/\n+\s*(?:[-*]|\d+[.)])\s+|\s+-\s+(?=[A-Z0-9])/)
        .map(item => item.replace(/^[-*]\s*/, "").trim())
        .filter(Boolean);

    if (items.length <= 1 && cleaned.includes(". ")) {
        items = cleaned
            .split(/(?<=\.)\s+(?=[A-Z])/)
            .map(item => item.trim())
            .filter(Boolean);
    }

    return items.slice(0, 8);
}

function renderEvidenceList(items, isGap, emptyMessage) {
    if (!items.length) {
        return `<p class="empty-state">${escapeHtml(emptyMessage)}</p>`;
    }

    return `
        <ul class="evidence-list">
            ${items.map(item => `
                <li class="evidence-item ${isGap ? "is-gap" : ""}">
                    <span class="evidence-marker"></span>
                    <p>${escapeHtml(item)}</p>
                </li>
            `).join("")}
        </ul>
    `;
}

function normalizeProjects(projects) {
    if (typeof projects === "string") {
        try {
            projects = JSON.parse(projects);
        } catch {
            projects = projects.trim() ? [projects] : [];
        }
    }

    if (!Array.isArray(projects)) return [];

    return projects
        .map(project => {
            if (project && typeof project === "object") {
                return {
                    name: project.name || project.title || "Project",
                    description: project.description || project.summary || project.details || "",
                    technologies: Array.isArray(project.technologies) ? project.technologies : [],
                };
            }

            return {
                name: "Project evidence",
                description: String(project || ""),
                technologies: [],
            };
        })
        .filter(project => project.description.trim() || project.name !== "Project")
        .slice(0, 6);
}

function renderProjects(projects) {
    if (!projects.length) {
        return `<p class="empty-state">No project evidence was extracted from the stored resume. Ask the candidate for project examples during screening.</p>`;
    }

    return `
        <div class="project-list">
            ${projects.map((project, index) => `
                <article class="project-item">
                    <h3>${escapeHtml(project.name)}</h3>
                    <p>${escapeHtml(compactProjectDescription(project.description, index))}</p>
                    ${renderToolRow(project.technologies)}
                </article>
            `).join("")}
        </div>
    `;
}

function renderExperienceEvidence(candidate, experienceValue, roleSignal, strengths, projects, evidenceText) {
    const companySignal = candidate.last_company_name
        || candidate.last_company
        || extractCompanySignal(evidenceText)
        || "Company not clearly listed";
    const yearsLabel = Number.isFinite(toNumber(experienceValue))
        ? formatExperience(experienceValue)
        : "Duration not explicitly listed";
    const roleLabel = candidate.designation || roleSignal || candidate.job_title || "Role signal needs review";
    const domainLabel = candidate.domain || candidate.industry || inferDomainFromEvidence(evidenceText);
    const workItems = experienceEvidenceItems(strengths, projects);

    return `
        <div class="experience-grid">
            ${experienceStat("Experience", yearsLabel)}
            ${experienceStat("Role signal", roleLabel)}
            ${experienceStat("Company signal", companySignal)}
            ${experienceStat("Domain", domainLabel)}
        </div>
        <div class="experience-history">
            <h3>Work evidence</h3>
            ${workItems.length
                ? `<ul>${workItems.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
                : `<p class="empty-state">No detailed work-history bullets were extracted. Verify dates, company, and ownership during screening.</p>`
            }
        </div>
    `;
}

function experienceStat(label, value) {
    return `
        <div class="experience-stat">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value || "Needs review")}</strong>
        </div>
    `;
}

function experienceEvidenceItems(strengths, projects) {
    const workPattern = /\b(experience|tenure|analyst|worked|managed|developed|built|created|automated|dashboard|reports?|marketing|retail|vendor|kpi|roi|inventory|sales)\b/i;
    const strengthItems = (strengths || [])
        .filter(item => workPattern.test(item))
        .map(item => compactProjectDescription(item, 2));
    const projectItems = (projects || [])
        .map(project => compactProjectDescription(project.description, 2))
        .filter(Boolean);

    return uniqueItems([...strengthItems, ...projectItems]).slice(0, 4);
}

function extractCompanySignal(text) {
    const match = String(text || "").match(/\b(?:at|with|for)\s+([A-Z][A-Za-z0-9&.,' -]{2,70}?)(?:\s+as|\s+during|,|\.|\n|$)/);
    if (!match) return "";
    return match[1].replace(/\s+/g, " ").trim();
}

function inferDomainFromEvidence(text) {
    const value = String(text || "").toLowerCase();
    if (value.includes("marketing")) return "Marketing analytics";
    if (value.includes("retail")) return "Retail analytics";
    if (value.includes("vendor")) return "Vendor analytics";
    if (value.includes("dashboard") || value.includes("kpi")) return "Data analytics";
    return "Domain needs review";
}

function compactProjectDescription(description, index) {
    const fallback = "Project details were mentioned but not described in the resume text.";
    const text = String(description || fallback).replace(/\s+/g, " ").trim();
    const limit = index >= 3 ? 210 : 260;
    if (text.length <= limit) return text;
    return `${text.slice(0, limit).trim()}...`;
}

function renderSignalGraph(score, confidence, matchedSkills, missingSkills, projects) {
    const matched = matchedSkills.length;
    const missing = missingSkills.length;
    const totalSkills = Math.max(matched + missing, 1);
    const skillCoverage = Math.round((matched / totalSkills) * 100);
    const projectDepth = Math.min(projects.length * 25, 100);
    const confidenceValue = Number.isFinite(confidence) ? Math.round(confidence) : Math.max(45, skillCoverage);
    const matchValue = Number.isFinite(score) ? Math.round(score) : Math.round((skillCoverage + projectDepth + confidenceValue) / 3);

    return `
        <div class="signal-graph">
            ${graphRow("Overall match", matchValue, "is-blue")}
            ${graphRow("Skill coverage", skillCoverage, "is-green")}
            ${graphRow("Project depth", projectDepth, "is-blue")}
            ${graphRow("Gap risk", Math.min(missing * 18, 100), "is-amber")}
        </div>
    `;
}

function graphRow(label, value, className) {
    const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
    return `
        <div class="graph-row">
            <div>
                <span>${escapeHtml(label)}</span>
                <strong>${safeValue}%</strong>
            </div>
            <div class="graph-track">
                <i class="${className}" style="width:${safeValue}%"></i>
            </div>
        </div>
    `;
}

function renderInterviewFocus(matchedSkills, missingSkills, projects, gaps) {
    const strongestSkill = matchedSkills[0] || "their strongest listed skill";
    const projectTheme = cleanProjectLabel(projects[0]) || "their most relevant project work";
    const missingSkill = missingSkills[0] || "the main missing requirement";
    const gap = gaps[0] || "the largest evidence gap";
    const prompts = [
        `Ask for a concise walkthrough of ${projectTheme}: problem, approach, tools used, and measurable impact.`,
        `Validate hands-on depth in ${strongestSkill} with one practical example, not just tool familiarity.`,
        `Check whether ${missingSkill} is truly missing or simply not written clearly in the resume.`,
        `Clarify this gap before the next stage: ${gap}`,
    ];

    return `
        <div class="focus-list">
            ${prompts.map((prompt, index) => `
                <div class="focus-item">
                    <span>${index + 1}</span>
                    <p>${escapeHtml(prompt)}</p>
                </div>
            `).join("")}
        </div>
    `;
}

function cleanProjectLabel(project) {
    const name = String(project?.name || "").trim();
    const description = String(project?.description || "").trim();
    if (name && !/^project evidence\s*\d*$/i.test(name)) return name;
    if (description) {
        const firstPart = description.split(/[.,]/)[0].trim();
        return firstPart.length > 12 && firstPart.length < 90 ? firstPart : "the strongest project example";
    }
    return "";
}

function projectsFromEvidence(items) {
    const projectWords = /\b(project|dashboard|automation|automated|built|developed|implemented|created|analytics|report|solution|pipeline|application|system)\b/i;

    return items
        .filter(item => projectWords.test(item))
        .map((item, index) => ({
            name: projectTitleFromText(item, index),
            description: item,
            technologies: extractTechnologies(item),
        }))
        .slice(0, 4);
}

function projectTitleFromText(text, index) {
    const beforeColon = String(text || "").split(":")[0].trim();
    if (beforeColon && beforeColon.length <= 56) return beforeColon;
    return `Project evidence ${index + 1}`;
}

function extractTechnologies(text) {
    const known = [
        "Python", "Pandas", "SQL", "Power BI", "Excel", "Tableau", "React",
        "Node", "FastAPI", "Django", "Flask", "AWS", "Azure", "GCP",
        "Docker", "PostgreSQL", "MySQL", "MongoDB", "API", "ETL",
        "Data Analysis", "Data Visualization", "Dashboard", "Analytics",
        "KPI", "CTR", "ROI", "Data Cleaning", "Data Pipeline",
    ];
    const normalized = String(text || "").toLowerCase();
    return known.filter(tool => normalized.includes(tool.toLowerCase()));
}

function extractMissingSkillNames(text) {
    const known = [
        "APIs", "Data pipelines", "Data cleaning", "AWS", "GCP", "Cloud platforms",
        "Advanced statistics", "Unstructured datasets", "Statistical concepts",
    ];
    const normalized = String(text || "").toLowerCase();
    return known.filter(skill => normalized.includes(skill.toLowerCase()));
}

function extractScore(text) {
    const match = String(text || "").match(/\b(?:score|scored|match)\D{0,20}(\d{1,3})(?:\s*\/\s*100|\s*%)?/i);
    if (!match) return NaN;
    const score = Number(match[1]);
    return Number.isFinite(score) && score <= 100 ? score : NaN;
}

function extractExperience(text) {
    const match = String(text || "").match(/\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b/i);
    return match ? Number(match[1]) : NaN;
}

function extractRoleSignal(text) {
    const source = String(text || "");
    const knownRoles = [
        "Digital Marketing Analyst",
        "Marketing Analyst",
        "Data Analyst",
        "Business Analyst",
        "Power BI Analyst",
        "Data Visualization Analyst",
        "Backend Developer",
        "Software Developer",
    ];
    const lower = source.toLowerCase();
    const role = knownRoles.find(item => lower.includes(item.toLowerCase()));
    if (role) return role;

    const match = source.match(/\b([A-Z][A-Za-z]+\s+){0,3}(Analyst|Developer|Engineer|Manager|Consultant|Specialist)\b/);
    return match ? match[0].trim() : "";
}

function firstFinite(...values) {
    return values.find(value => Number.isFinite(value));
}

function firstPositive(...values) {
    return values.find(value => Number.isFinite(value) && value > 0);
}

function estimateScoreFromEvidence(matchedSkills, missingSkills, projects) {
    const matched = matchedSkills.length;
    const missing = missingSkills.length;
    if (!matched && !missing && !projects.length) return NaN;

    const skillCoverage = matched / Math.max(matched + missing, 1);
    const projectDepth = Math.min(projects.length / 4, 1);
    const gapPenalty = Math.min(missing * 4, 22);
    const score = Math.round((skillCoverage * 58) + (projectDepth * 30) + 12 - gapPenalty);
    return Math.max(35, Math.min(88, score));
}

function uniqueItems(items) {
    const seen = new Set();
    return items
        .map(item => String(item || "").trim())
        .filter(Boolean)
        .filter(item => {
            const key = item.toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
}

function hasSkillOverlap(skill, skillList) {
    const key = normalizeSkillKey(skill);
    return skillList.some(item => {
        const itemKey = normalizeSkillKey(item);
        return key === itemKey || key.includes(itemKey) || itemKey.includes(key);
    });
}

function normalizeSkillKey(value) {
    const key = String(value || "")
        .toLowerCase()
        .replace(/apis?\b/g, "api")
        .replace(/\bcloud platforms?\b/g, "cloud")
        .replace(/\bdata pipelines?\b/g, "pipeline")
        .replace(/[^a-z0-9]+/g, "");
    return key.endsWith("s") ? key.slice(0, -1) : key;
}

function renderToolRow(tools) {
    const cleanTools = Array.isArray(tools)
        ? tools.map(tool => String(tool || "").trim()).filter(Boolean).slice(0, 8)
        : [];

    if (!cleanTools.length) return "";

    return `
        <div class="pill-row">
            ${cleanTools.map(tool => `<span>${escapeHtml(tool)}</span>`).join("")}
        </div>
    `;
}

function renderSkillCloud(title, skills, emptyMessage) {
    return `
        <div class="skill-block">
            <h3>${escapeHtml(title)}</h3>
            ${skills.length
                ? `<div class="skill-cloud">${skills.slice(0, 18).map(skill => `<span>${escapeHtml(skill)}</span>`).join("")}</div>`
                : `<p class="empty-state">${escapeHtml(emptyMessage)}</p>`
            }
        </div>
    `;
}

function splitSkillText(value) {
    return String(value || "")
        .split(/[,|]/)
        .map(skill => skill.trim())
        .filter(Boolean);
}

function toNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : NaN;
}

function formatExperience(value) {
    const years = toNumber(value);
    if (!Number.isFinite(years)) return "Not listed";
    return `${years} ${years === 1 ? "year" : "years"}`;
}

function formatGeneratedTime(value) {
    if (!value) return "Saved report";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Saved report";
    return date.toLocaleString([], {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function regenerateReport() {
    const params = new URLSearchParams(window.location.search);
    const resumeId = params.get("resume_id");
    if (!resumeId) return;

    const ok = window.confirm("Regenerate this AI report? This will make a fresh AI call and replace the saved explanation.");
    if (!ok) return;

    sessionStorage.removeItem(reportCacheKey(resumeId));
    loadExplanationPage({ forceRefresh: true });
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showError(container, message) {
    container.style.display = "block";
    container.innerHTML = `<div class="error-state">${escapeHtml(message)}</div>`;
}

function goBack() {
    window.history.back();
}
