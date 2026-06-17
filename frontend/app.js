

let dashboardJobs = []
let bulkResults=[]
let bulkWorkflowState = createEmptyBulkWorkflowState()
let currentBulkSessionId = null
const BULK_ACTIVE_SESSION_KEY = "atsBulkActiveSession:v1"
const BULK_HISTORY_KEY = "atsBulkHistory:v1"
let charts={}
let insightCharts={}
let jobChart = null
let currentResults = []  
let currentSkills = []
let interviewDashboardCandidates = []
let candidateProfileStore = {}
let currentShortlistResults = []
let shortlistAnalyticsCharts = {}
let currentShortlistExplanation = null
let latestSourcingData = null
let candidateProfileReturnContext = {
label: "Back to Candidates",
action: "showPage('results')"
}
let jdAutofillTimer = null
let lastParsedJDText = ""
let dashboardLoadPromise = null
let lastDashboardLoadAt = 0

function safeText(value){
return String(value ?? "")
}

function candidateRecruiterScore(candidate){
return Number(candidate?.final_score ?? candidate?.score ?? candidate?.rank_score ?? candidate?.recruiter_rank_score ?? 0) || 0
}

function compareCandidateRank(a,b){
return candidateRecruiterScore(b) - candidateRecruiterScore(a)
}

function safeHtml(value){
return safeText(value)
.replace(/&/g,"&amp;")
.replace(/</g,"&lt;")
.replace(/>/g,"&gt;")
.replace(/"/g,"&quot;")
.replace(/'/g,"&#039;")
}

function safeJs(value){
return safeText(value).replace(/\\/g,"\\\\").replace(/'/g,"\\'")
}

function shortText(value, max=34){
let text = safeText(value).trim()
return text.length > max ? text.slice(0, max - 3) + "..." : text
}

const ATS_SKILL_PATTERNS = [
["Google Apps Script", /\bgoogle\s+apps?\s+script\b/i],
["Power Query", /\bpower\s+query\b/i],
["Power BI", /\bpower\s*bi\b|\bpowerbi\b/i],
["Excel", /\b(?:(?:ms|microsoft)\s+)?excel\b/i],
["SQL", /\bsql(?:\s+queries|\s+query)?\b/i],
["Python", /\bpython\b/i],
["Pandas", /\bpandas\b/i],
["NumPy", /\bnumpy\b|\bnum\s*py\b/i],
["Matplotlib", /\bmatplotlib\b/i],
["Seaborn", /\bseaborn\b/i],
["Tableau", /\btableau\b/i],
["DAX", /\bdax\b/i],
["JavaScript", /\bjava\s*script\b|\bjavascript\b/i],
["Statistics", /\bstatistics?\b/i],
["EDA", /\beda\b|\bexploratory\s+data\s+analysis\b/i],
["Data Cleaning", /\bdata\s+clean(?:ing)?\b/i],
["Data Extraction", /\bdata\s+extract(?:ion)?\b/i],
["Data Visualization", /\bdata\s+visuali[sz]ation\b|\bdashboard(?:ing)?\b/i],
["Data Analysis", /\bdata\s+analys(?:is|tics)\b|\banalytics?\b/i],
["Data Handling", /\bdata\s+handling\b/i],
["Problem Solving", /\bproblem\s+solving\b/i],
["Communication", /\bcommunication\b/i],
["Presentation", /\bpresentation\b/i],
["Attention to Detail", /\battention\s+to\s+detail\b/i],
["Analytical Thinking", /\banalytical\s+(?:and\s+logical\s+)?thinking\b|\blogical\s+thinking\b/i]
]

function titleCaseSkill(value){
let text = safeText(value).trim()
if(!text) return ""
let upperWords = new Set(["sql","dax","eda","api","aws","gcp","ui","ux"])
return text
.split(/\s+/)
.map(word=>{
let clean = word.toLowerCase()
if(upperWords.has(clean)) return clean.toUpperCase()
if(clean === "numpy") return "NumPy"
if(clean === "pandas") return "Pandas"
return clean.charAt(0).toUpperCase() + clean.slice(1)
})
.join(" ")
}

function addUniqueSkill(output, seen, skill){
let clean = safeText(skill).trim()
if(!clean) return
let key = clean.toLowerCase()
if(seen.has(key)) return
seen.add(key)
output.push(clean)
}

function normalizeLooseSkillPhrase(value){
let text = safeText(value)
.replace(/[_]/g," ")
.replace(/[(){}\[\]]/g," ")
.replace(/\b(?:basic|beginner|intermediate|advanced|expert|strong|good|excellent|hands[-\s]?on|required|mandatory|preferred|must\s+have|nice\s+to\s+have|knowledge\s+of|understanding\s+of|familiarity\s+with|experience\s+with|skills?|queries?|query|tools?|concepts?|level|to|and|or|in|with|using)\b/ig," ")
.replace(/[^\w\s.+#/-]/g," ")
.replace(/\s+/g," ")
.trim()

if(!text || text.length > 35 || text.split(/\s+/).length > 3){
return ""
}

return titleCaseSkill(text)
}

function normalizeScreeningSkills(values, jdText=""){
let sources = []
if(Array.isArray(values)){
sources = values
}else if(values){
sources = safeText(values).split(/[,;|\n]+/)
}
if(jdText) sources.push(jdText)

let seen = new Set()
let output = []

sources.forEach(source=>{
let text = safeText(source).trim()
if(!text) return

ATS_SKILL_PATTERNS.forEach(([label, pattern])=>{
if(pattern.test(text)){
addUniqueSkill(output, seen, label)
}
})

if(!ATS_SKILL_PATTERNS.some(([, pattern])=>pattern.test(text))){
addUniqueSkill(output, seen, normalizeLooseSkillPhrase(text))
}
})

return output
}

function getNumericInputValue(id){
let el = document.getElementById(id)
if(!el || el.value === "" || el.value === null || el.value === undefined) return null
let value = Number(el.value)
return Number.isFinite(value) ? value : null
}

function candidateInitials(name){
let text = safeText(name).trim()
if(!text) return "NA"
return text
.split(/\s+/)
.slice(0,2)
.map(part=>part.charAt(0).toUpperCase())
.join("") || "NA"
}

function normalizeList(value){
if(!value) return []
if(Array.isArray(value)){
return value.map(item=>safeText(item).trim()).filter(Boolean)
}
let text = safeText(value).trim()
if(!text) return []
try{
let parsed = JSON.parse(text)
if(Array.isArray(parsed)){
return parsed.map(item=>safeText(item).trim()).filter(Boolean)
}
}catch{}
return text
.split(/[,|;]+/)
.map(item=>item.trim())
.filter(Boolean)
}

function uniqueCleanList(values){
let seen = new Set()
let output = [];
(values || []).forEach(value=>{
let clean = safeText(value).trim()
if(!clean) return
let key = clean.toLowerCase()
if(seen.has(key)) return
seen.add(key)
output.push(clean)
})

return output
}

const ATS_TRANSFERABLE_SKILL_GROUPS = [
["Power BI","Tableau","Looker","Qlik"],
["Excel","Google Sheets"],
["SQL","PostgreSQL","MySQL","SQL Server"],
["Python","Pandas","NumPy"],
["Communication","Presentation"]
]

function skillLabelsInText(value){
let text = safeText(value)
let labels = []

ATS_SKILL_PATTERNS.forEach(([label, pattern])=>{
if(pattern.test(text)){
labels.push(label)
}
})

return uniqueCleanList(labels)
}

function candidateCoversSkill(skill, candidateSkills){
let target = safeText(skill).trim().toLowerCase()
let candidates = (candidateSkills || []).map(item=>safeText(item).trim().toLowerCase()).filter(Boolean)

if(!target) return false
if(candidates.includes(target)) return true

return ATS_TRANSFERABLE_SKILL_GROUPS.some(group=>{
let normalizedGroup = group.map(item=>item.toLowerCase())
return normalizedGroup.includes(target) && candidates.some(skillName=>normalizedGroup.includes(skillName))
})
}

function candidateCoverageLabel(skill, candidateSkills){
let target = safeText(skill).trim().toLowerCase()
let cleanCandidateSkills = (candidateSkills || []).map(item=>safeText(item).trim()).filter(Boolean)
let exact = cleanCandidateSkills.find(item=>item.toLowerCase() === target)
if(exact) return exact

for(let group of ATS_TRANSFERABLE_SKILL_GROUPS){
let normalizedGroup = group.map(item=>item.toLowerCase())
if(!normalizedGroup.includes(target)) continue
let transferable = cleanCandidateSkills.find(item=>normalizedGroup.includes(item.toLowerCase()))
if(transferable) return transferable
}

return skill
}

function expandSkillSignal(value){
let labels = skillLabelsInText(value)
return labels.length ? labels : [titleCaseSkill(value)].filter(Boolean)
}

function buildCandidateSkillSignals(candidate){
let rawMatched = normalizeList(candidate?.matched_skills)
let rawMissing = normalizeList(candidate?.missing_skills)
let rawSkills = normalizeList(candidate?.key_skills)
let candidateCoverage = uniqueCleanList(
[
...rawSkills.flatMap(expandSkillSignal),
...rawMatched.flatMap(expandSkillSignal)
]
)
let matched = rawMatched.length
? uniqueCleanList(rawMatched.flatMap(expandSkillSignal))
: candidateCoverage.slice(0, 12)
let missing = []

rawMissing.forEach(item=>{
let expanded = expandSkillSignal(item)
expanded.forEach(skill=>{
if(candidateCoversSkill(skill, candidateCoverage)){
matched.push(candidateCoverageLabel(skill, candidateCoverage))
}else{
missing.push(skill)
}
})
})

return {
matched: uniqueCleanList(matched),
missing: uniqueCleanList(missing),
candidateCoverage
}
}

function cleanedCandidateMissingSkills(candidate){
return buildCandidateSkillSignals(candidate || {}).missing
}

function cleanedCandidateMatchedSkills(candidate){
let signals = buildCandidateSkillSignals(candidate || {})
return signals.matched.length ? signals.matched : signals.candidateCoverage
}

function createEmptyBulkWorkflowState(){
return {
shortlist: {},
communication: {},
interview: {}
}
}

function candidateResultSearchText(candidate){
let skillSignals = buildCandidateSkillSignals(candidate || {})
return uniqueCleanList([
candidate?.full_name,
candidate?.email,
candidate?.phone,
candidate?.location,
candidate?.designation,
candidate?.last_company_name,
candidate?.education,
candidate?.industry,
candidate?.domain,
getDisplayStatus(candidate || {}),
...skillSignals.candidateCoverage,
...skillSignals.matched,
...skillSignals.missing
]).join(" ").toLowerCase()
}

function textList(items, fallback="not listed"){
let clean = uniqueCleanList(items)
return clean.length ? clean.join(", ") : fallback
}

function getCandidateProfileReturnContext(trigger){
if(trigger?.closest("#topCandidateTable")) return {label:"Back to Top Candidates", action:"openTopCandidates()"}
if(trigger?.closest("#resultsTable")) return {label:"Back to Candidate Results", action:"showPage('jobResult')"}
if(trigger?.closest("#shortlistTable")) return {label:"Back to Shortlist", action:"showPage('results')"}
if(trigger?.closest("#communicationResultsTable, #pendingTable, #interestedTable, #notInterestedTable, #communicationTableBody, #commTable")) return {label:"Back to Communication", action:"showPage('communicationResults')"}
if(trigger?.closest("#interviewDashboardTable")) return {label:"Back to Interview Dashboard", action:"showPage('interviewDashboard')"}
if(trigger?.closest("#bulkResultsTable, #top10Table")) return {label:"Back to Bulk Analyzer", action:"showPage('bulk')"}
return {label:"Back to Candidates", action:"showPage('results')"}
}

window.openRankedCandidateProfile = candidateId => openRankedCandidateProfile(candidateId)
if(!window.__rankedCandidateProfileClickBound){
document.addEventListener("click", event => {
let trigger = event.target.closest("[data-profile-candidate-id]")
if(!trigger) return

event.preventDefault()
candidateProfileReturnContext = getCandidateProfileReturnContext(trigger)
openRankedCandidateProfile(trigger.dataset.profileCandidateId || "")
})
window.__rankedCandidateProfileClickBound = true
}

function scoreBand(score, candidate={}){
let value = Number(score) || 0
let status = safeText(candidate.status || candidate.current_stage || "").toLowerCase()
let reason = safeText(candidate.ranking_reason || candidate.ai_confidence_reason || candidate.explanation || "").toLowerCase()
let flags = normalizeList(candidate.recruiter_flags || candidate.parser_flags || candidate.risk_points || []).join(" ").toLowerCase()
let combined = `${status} ${reason} ${flags}`
if(combined.includes("parser quality") || combined.includes("profile needs review") || combined.includes("name_needs_review") || combined.includes("company_needs_review") || combined.includes("project_noise_detected")) return {label:"Profile needs review", className:"is-review"}
if(combined.includes("slightly_over_range") || combined.includes("slightly above")) return {label:"Slightly above range", className:"is-review"}
if(combined.includes("strong_overqualified") || combined.includes("overqualified_review") || combined.includes("overqualified")) return {label:"Overqualified review", className:"is-review"}
if(combined.includes("missing_core_skills") || combined.includes("missing or weak core") || combined.includes("skill validation")) return {label:"Skill validation needed", className:"is-review"}
if(value >= 85 && status.includes("shortlist")) return {label:"Strong fit", className:"is-strong"}
if(value >= 75) return {label:"Good match", className:"is-good"}
if(value >= 60) return {label:"Review required", className:"is-review"}
return {label:"Low match", className:"is-low"}
}

function topCandidateDetail(label, value){
return `
<div class="ats-candidate-detail">
<span>${safeHtml(label)}</span>
<strong>${safeHtml(value || "-")}</strong>
</div>
`
}

function candidateSafeDisplay(candidate, key, fallback="Needs validation"){
let safe = candidate?.safe_display || {}
let value = safe[key]
if(value && value !== "Needs validation") return value
if(key === "name") return candidate?.full_name || candidate?.name || fallback
if(key === "email") return candidate?.email || fallback
if(key === "phone") return candidate?.phone || fallback
if(key === "location") return candidate?.location || fallback
if(key === "last_company") return candidate?.last_company_name || fallback
if(key === "education") return candidate?.education || fallback
if(key === "experience"){
let relevant = Number(candidate?.relevant_experience_years)
let years = Number(candidate?.total_experience_years)
let direct = Number(candidate?.direct_relevant_experience_years)
let isTransition = Boolean(candidate?.transition_candidate) || candidate?.experience_relevance_label === "transferable_reporting"
if(Number.isFinite(relevant) && relevant >= 0 && (isTransition || (Number.isFinite(years) && Math.abs(years - relevant) > 0.25))){
let label = `${relevant} years JD-related`
if(Number.isFinite(years) && years > 0) label += ` (${years} total)`
if(Number.isFinite(direct) && direct === 0) label += `; direct DA not proven`
return label
}
return Number.isFinite(years) && years > 0 ? `${years} years` : fallback
}
return value || fallback
}

function topCandidateSkillPills(skills){
if(skills.length === 0){
return `<span class="ats-muted-copy">No skills found in this profile.</span>`
}
return skills.slice(0,18).map(skill=>`<span>${safeHtml(skill)}</span>`).join("")
}

function topCandidateProjectEvidence(projects=null, isLoading=false){
if(isLoading){
return `
<div class="ats-project-evidence-list">
<div class="ats-project-evidence-item is-loading">
<span>AI</span>
<p>Finding project evidence from resume data...</p>
</div>
</div>
`
}

if(typeof projects === "string"){
try{
projects = JSON.parse(projects)
}catch{
projects = projects.trim() ? [projects] : []
}
}

let items = Array.isArray(projects) ? projects.filter(item=>safeText(item).trim()) : []

if(items.length === 0){
items = ["No concrete project details were found in the stored resume text. Ask the candidate to share project examples during screening."]
}

return `
<div class="ats-project-evidence-list">
${items.slice(0,4).map(item=>{
let text = ""
if(item && typeof item === "object"){
let tech = Array.isArray(item.technologies) && item.technologies.length
? ` Tools: ${item.technologies.slice(0,6).join(", ")}.`
: ""
text = `${item.name || "Project"}: ${item.description || ""}${tech}`
}else{
text = safeText(item)
}
return `
<div class="ats-project-evidence-item">
<span>PRJ</span>
<p>${safeHtml(text)}</p>
</div>
`
}).join("")}
</div>
`
}

function topCandidateSkillCoverage(candidate){
let signals = buildCandidateSkillSignals(candidate || {})
let matched = signals.matched
let missing = signals.missing
let extracted = signals.candidateCoverage
let matchPercent = Number(candidate.skill_match_percent)
let total = matched.length + missing.length
if(total){
matchPercent = total ? Math.round((matched.length / total) * 100) : candidateRecruiterScore(candidate)
}else if(!Number.isFinite(matchPercent)){
matchPercent = candidateRecruiterScore(candidate)
}
matchPercent = Math.min(Math.max(matchPercent,0),100)
let missingPercent = Math.max(0, 100 - matchPercent)

return `
<div class="ats-candidate-panel ats-candidate-coverage-panel">
<div class="ats-panel-title-row">
<div>
<h4>JD Skill Coverage</h4>
<p>Matched and missing skills from JD vs resume evidence.</p>
</div>
<span>${safeHtml(formatPercent(matchPercent))}</span>
</div>

<div class="ats-skill-graph">
<div class="ats-skill-graph-row">
<div>
<strong>Matched Skills</strong>
<span>${matched.length || extracted.length} found</span>
</div>
<div class="ats-skill-bar"><span style="width:${matchPercent}%"></span></div>
</div>
<div class="ats-skill-graph-row is-gap">
<div>
<strong>Skill Gaps</strong>
<span>${missing.length} to verify</span>
</div>
<div class="ats-skill-bar"><span style="width:${missingPercent}%"></span></div>
</div>
</div>

<div class="ats-gap-skill-list">
${missing.length ? missing.slice(0,8).map(skill=>`<span>${safeHtml(skill)}</span>`).join("") : `<span class="is-clear">No major JD skill gaps listed</span>`}
</div>
</div>
`
}

function topCandidateRecommendation(score, recommendation=null, isLoading=false){
if(isLoading){
return `
<li>
<span class="ats-signal-icon">AI</span>
<span>Generating JD-based recommendation...</span>
</li>
`
}

let strengths = recommendation && Array.isArray(recommendation.strengths)
? recommendation.strengths
: []
let gaps = recommendation && Array.isArray(recommendation.gaps)
? recommendation.gaps
: []
let projects = recommendation && Array.isArray(recommendation.project_evidence)
? recommendation.project_evidence
: []
let detail = recommendation && recommendation.detailed_assessment
? safeText(recommendation.detailed_assessment)
: ""

if(strengths.length === 0){
let value = Number(score) || 0
strengths = value >= 65
? ["Stored scoring shows a strong JD skill match","Resume profile has relevant screening signals","Use resume evidence and project details before final hiring decision"]
: ["Stored scoring shows limited JD alignment","Review matched skills, missing skills, and resume/project evidence before moving forward","Candidate may need additional screening against mandatory JD requirements"]
}

if(gaps.length === 0){
gaps = ["Verify advanced or mandatory skills during recruiter review."]
}

let strengthHtml = strengths.slice(0,4).map(item=>`
<li>
<span class="ats-signal-icon">OK</span>
<span>${safeHtml(item)}</span>
</li>
`).join("")

let projectHtml = projects.slice(0,3).map(item=>`
<li class="is-project">
<span class="ats-signal-icon">PRJ</span>
<span>${safeHtml(item)}</span>
</li>
`).join("")

let detailHtml = detail ? `
<li class="is-detail">
<span class="ats-signal-icon">AI</span>
<span>${safeHtml(detail)}</span>
</li>
` : ""

let gapHtml = gaps.slice(0,3).map(item=>`
<li class="is-gap">
<span class="ats-signal-icon">GAP</span>
<span>${safeHtml(item)}</span>
</li>
`).join("")

return detailHtml + strengthHtml + projectHtml + gapHtml
}

async function loadTopCandidateRecommendation(jobId, resumeId, score){
let list = document.getElementById("topCandidateAiList")
let statusPill = document.getElementById("topCandidateAiStatus")
let summary = document.getElementById("topCandidateAiSummary")
let projectBox = document.getElementById("topCandidateProjects")

if(!list || !resumeId) return

try{
let res = await fetch(API + "/top-candidate-recommendation/" + encodeURIComponent(jobId) + "/" + encodeURIComponent(resumeId))
let recommendation = await res.json()

if(!res.ok){
throw new Error(recommendation.detail || "AI recommendation failed")
}

if(statusPill){
statusPill.innerText = recommendation.verdict || statusPill.innerText
}

if(summary && recommendation.summary){
summary.innerText = recommendation.summary
}

if(projectBox){
projectBox.innerHTML = topCandidateProjectEvidence(recommendation.project_evidence)
}

list.innerHTML = topCandidateRecommendation(score, recommendation)
}catch(error){
try{
let fallbackRes = await fetch(API + "/ai-explanation/" + encodeURIComponent(resumeId))
let fallbackData = await fallbackRes.json()
let explanation = safeText(fallbackData.explanation || "").trim()
if(projectBox && Array.isArray(fallbackData.projects) && fallbackData.projects.length){
projectBox.innerHTML = topCandidateProjectEvidence(fallbackData.projects)
}

if(explanation){
let firstLine = explanation.split(/\n+/).map(line=>line.trim()).find(Boolean) || explanation
if(summary){
summary.innerText = firstLine.replace(/^Summary:\s*/i, "")
}
list.innerHTML = `
<li class="is-detail">
<span class="ats-signal-icon">AI</span>
<span>${safeHtml(explanation)}</span>
</li>
`
if(projectBox && !(Array.isArray(fallbackData.projects) && fallbackData.projects.length)){
projectBox.innerHTML = topCandidateProjectEvidence([])
}
return
}
}catch(fallbackError){
}

if(summary){
summary.innerText = "AI recommendation generated from available JD, score, matched skills, and missing skill signals."
}
list.innerHTML = topCandidateRecommendation(score, {
detailed_assessment:"OpenAI summary is not available from the live server yet, so this recommendation is based on stored JD matching, candidate score, matched skills, and missing skills.",
strengths:[],
gaps:[]
})
if(projectBox){
projectBox.innerHTML = topCandidateProjectEvidence([])
}
}
}

async function shortlistTopCandidate(resumeId, jobId){
if(!resumeId){
alert("Candidate id missing.")
return
}

let button = typeof event !== "undefined" ? event.currentTarget : null
setButtonLoading(button, true, "Shortlisting...")

try{
let res = await fetch(API + "/shortlist/" + encodeURIComponent(resumeId), {
method:"POST",
headers:authHeaders()
})
let data = await res.json()

if(!res.ok || data.error){
alert(data.detail || data.error || "Could not shortlist candidate")
return
}

let statusPill = document.getElementById("topCandidateAiStatus")
if(statusPill) statusPill.innerText = "Shortlisted"

let profileStatus = document.getElementById("topCandidateProfileStatus")
if(profileStatus) profileStatus.innerText = "Shortlisted"

if(button){
button.innerText = "Shortlisted"
button.disabled = true
button.classList.add("is-done")
}

await refreshRecruiterWorkflow(jobId)
}catch(error){
alert("Could not shortlist candidate")
}finally{
if(button && !button.classList.contains("is-done")){
setButtonLoading(button, false)
}
}
}

function setButtonLoading(button, isLoading, text="Loading..."){
if(!button) return
if(isLoading){
button.dataset.originalText = button.innerText
button.disabled = true
button.innerText = text
}else{
button.disabled = false
button.innerText = button.dataset.originalText || button.innerText
}
}

async function refreshRecruiterWorkflow(jobId){
await Promise.allSettled([
loadDashboard(),
loadShortlistJobDropdown(),
jobId ? loadShortlistedCandidates() : Promise.resolve(),
loadCommunicationJobs(),
jobId ? loadCommunicationSplit(jobId) : Promise.resolve()
])
}

// ---------------- PAGE SWITCH ----------------
function setActiveNavForPage(page){
let navMap = {
dashboard: "Jobs",
job: "Jobs",
editJob: "Jobs",
applyJob: "Jobs",
deleteJobs: "Jobs",
jobPosts: "Jobs",
results: "Recruiter",
jobResult: "Recruiter",
topCandidate: "Recruiter",
candidateProfile: "Recruiter",
allJobs: "Recruiter",
insight: "Recruiter",
shortlistAnalytics: "Recruiter",
shortlistExplanation: "Recruiter",
bulk: "Bulk Analyzer",
communication: "Outreach",
communicationResults: "Outreach",
interviewDashboard: "Interview Dashboard"
}

let label = navMap[page]
document.querySelectorAll(".nav-btn").forEach(btn => {
let isActive = label && safeText(btn.innerText).includes(label)
btn.classList.toggle("active", Boolean(isActive))
})
}

function resetPageScroll(){
requestAnimationFrame(()=>{
window.scrollTo({top:0,left:0,behavior:"auto"})
let main = document.querySelector("body > .w-full > .flex-1")
if(main) main.scrollTop = 0
})
}

function showPage(page){

// hide pages
let pages=[
"dashboardPage",
"candidateProfilePage",
"candidateAIProfilePage",
"jobPage",
"editJobPage",
"bulkPage",
"resultsPage",
"jobResultPage",
"applyJobPage",
"jobPostsPage",
"insightPage",
"shortlistAnalyticsPage",
"shortlistExplanationPage",
"editFormPage",
"topCandidatePage",
"allJobsPage",
"deleteJobsPage",
"communicationPage",
"communicationResultsPage",
"interviewDashboardPage",

]
pages.forEach(id=>{
let el=document.getElementById(id)
if(el){
el.classList.add("hidden")
}
})

let target=document.getElementById(page+"Page")

if(target){
target.classList.remove("hidden")
}

document.body.classList.toggle("ats-candidate-profile-mode", page === "candidateProfile")
if(page === "candidateProfile"){
let dashboardPage = document.getElementById("dashboardPage")
if(dashboardPage) dashboardPage.classList.remove("hidden")
}

document.body.classList.toggle(
"ats-focus-page",
[
"jobResult",
"topCandidate",
"candidateProfile",
"insight",
"shortlistAnalytics",
"shortlistExplanation",
"allJobs",
"communication",
"communicationResults",
"interviewDashboard"
].includes(page)
)
setActiveNavForPage(page)
resetPageScroll()

// recruiter dashboard
// recruiter dashboard
if(page==="results"){

loadJobs()

loadShortlistJobDropdown()

setTimeout(()=>{
loadShortlistedCandidates()
},300)

}



if(page==="communication"){
    loadCommunicationJobs()   // * NEW FUNCTION
    updateGmailConnectStatus()


}

if(page==="interviewDashboard"){
    loadInterviewDashboard()
}

if(page === "dashboard"){
    loadDashboard()
}

if(page === "bulk"){
    restoreBulkSessionFromStorage()
}

// EDIT JOB PAGE
if(page==="editJob"){
loadEditJobs()
}

if(page==="applyJob"){
loadApplyJobs()
}

if(page==="deleteJobs"){
loadDeleteJobs()
}

window.scrollTo(0,0)

}


function authHeaders(){
return {
    "Content-Type": "application/json",
    "Authorization": "Bearer " + localStorage.getItem("token")
}
}

function getRecruiterEmailFromSession(){
let token = localStorage.getItem("token")
let payload = typeof parseJwt === "function" ? parseJwt(token) : null
let tokenEmail = payload?.email || ""
if(tokenEmail){
    localStorage.setItem("userEmail", tokenEmail)
    return tokenEmail
}

return localStorage.getItem("userEmail") || ""
}

const HIRE_SCORE_DEFAULT_FROM_EMAIL = "support@hirescoreai.com"
const HIRE_SCORE_DEFAULT_FROM_NAME = "HireScore AI"
const OUTREACH_SENDER_CONFIG_KEY = "outreachSenderConfig:v2"
let ownDomainDraft = null

function normalizeSenderDomain(value){
let domain = safeText(value).trim().toLowerCase()
domain = domain.replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0].split(":")[0]
if(domain.includes("@")) domain = domain.split("@").pop()
return domain
}

function domainFromEmail(email){
let parts = safeText(email).trim().toLowerCase().split("@")
return parts.length === 2 ? normalizeSenderDomain(parts[1]) : ""
}

function readOutreachSenderConfig(){
try{
    let parsed = JSON.parse(localStorage.getItem(OUTREACH_SENDER_CONFIG_KEY) || "null")
    if(parsed && typeof parsed === "object") return parsed
}catch(e){}
let legacyReplyTo = safeText(localStorage.getItem("outreachSenderEmail")).trim()
let recruiterEmail = getRecruiterEmailFromSession()
return {
    mode: "hirescore",
    active: true,
    from_email: HIRE_SCORE_DEFAULT_FROM_EMAIL,
    from_name: HIRE_SCORE_DEFAULT_FROM_NAME,
    reply_to: legacyReplyTo || recruiterEmail,
    sender_name: ""
}
}

function writeOutreachSenderConfig(config){
localStorage.setItem(OUTREACH_SENDER_CONFIG_KEY, JSON.stringify(config))
if(config?.reply_to){
    localStorage.setItem("outreachSenderEmail", config.reply_to)
}
updateGmailConnectStatus()
}

function getOutreachSenderEmail(){
let config = readOutreachSenderConfig()
if(config.mode === "own_domain" && config.verification_status === "verified"){
    return safeText(config.from_email).trim()
}
return safeText(config.reply_to).trim() || getRecruiterEmailFromSession() || ""
}

function getReplySyncEmail(){
return safeText(localStorage.getItem("gmailConnectedEmail")).trim()
    || safeText(readOutreachSenderConfig().reply_to).trim()
    || safeText(localStorage.getItem("outreachSenderEmail")).trim()
    || getRecruiterEmailFromSession()
}

function getActiveSenderPayload(){
let config = readOutreachSenderConfig()
if(config.mode === "own_domain"){
    return {
        sender_mode: "own_domain",
        from_email: safeText(config.from_email).trim(),
        from_name: safeText(config.sender_name || config.from_name).trim(),
        reply_to: safeText(config.from_email).trim(),
        domain: normalizeSenderDomain(config.domain),
        verification_status: config.verification_status || "pending"
    }
}
return {
    sender_mode: "hirescore",
    from_email: HIRE_SCORE_DEFAULT_FROM_EMAIL,
    from_name: HIRE_SCORE_DEFAULT_FROM_NAME,
    reply_to: safeText(config.reply_to).trim() || getRecruiterEmailFromSession(),
    sender_display_name: safeText(config.sender_name).trim()
}
}

function saveOutreachSenderEmail(){
let input = document.getElementById("outreachSenderEmail")
let email = safeText(input?.value || readOutreachSenderConfig().reply_to).trim()
if(email){
    localStorage.setItem("outreachSenderEmail", email)
}else{
    localStorage.removeItem("outreachSenderEmail")
}
let config = readOutreachSenderConfig()
if(config.mode === "hirescore"){
    localStorage.setItem(OUTREACH_SENDER_CONFIG_KEY, JSON.stringify({ ...config, reply_to: email }))
}
let connectedEmail = safeText(localStorage.getItem("gmailConnectedEmail")).trim().toLowerCase()
if(connectedEmail && email.toLowerCase() !== connectedEmail){
    localStorage.removeItem("gmailConnected")
}
updateGmailConnectStatus()
}

function offerGoogleReconnect(message){
let prompt = (message || "Google/Gmail permission is required.") + "\n\nConnect Gmail/Google now?"
if(confirm(prompt)){
    openReplySyncModal()
}
}

function removeSenderSetupModal(){
document.getElementById("senderSetupModal")?.remove()
}

function senderModalShell(title, description, bodyHtml){
removeSenderSetupModal()
let modal = document.createElement("div")
modal.id = "senderSetupModal"
modal.className = "ats-sender-modal"
modal.innerHTML = `
<div class="ats-sender-modal-card">
<div class="ats-sender-modal-head">
<div>
<h3>${safeHtml(title)}</h3>
<p>${safeHtml(description)}</p>
</div>
<button type="button" class="ats-sender-modal-close" onclick="removeSenderSetupModal()">Close</button>
</div>
${bodyHtml}
</div>`
document.body.appendChild(modal)
}

function openHireScoreSenderModal(){
let config = readOutreachSenderConfig()
let replyTo = safeText(config.reply_to).trim() || getRecruiterEmailFromSession()
let displayName = safeText(config.sender_name).trim()
senderModalShell(
    "Use HireScore AI Sender",
    "No DNS setup needed. Candidate emails will be sent from HireScore AI, and replies will go to your email.",
    `
<div class="ats-sender-recommended">Recommended default sender</div>
<div class="ats-sender-preview-box">
<div><span>From</span><strong>HireScore AI &lt;${HIRE_SCORE_DEFAULT_FROM_EMAIL}&gt;</strong></div>
<div><span>Reply-To</span><strong id="hireScoreReplyPreview">${safeHtml(replyTo || "recruiter@email.com")}</strong></div>
</div>
<label class="ats-sender-field">
<span>Reply-to email</span>
<input id="hireScoreReplyToInput" type="email" value="${safeHtml(replyTo)}" placeholder="recruiter@email.com" oninput="updateHireScoreReplyPreview()">
</label>
<label class="ats-sender-field">
<span>Sender display name optional</span>
<input id="hireScoreDisplayNameInput" type="text" value="${safeHtml(displayName)}" placeholder="Recruiting Team">
</label>
<div class="ats-sender-actions">
<button type="button" class="ats-gmail-connect-btn is-secondary" onclick="saveHireScoreSender(false)">Save</button>
<button type="button" class="ats-gmail-connect-btn" onclick="saveHireScoreSender(true)">Set as Active Sender</button>
</div>`
)
}

function updateHireScoreReplyPreview(){
let value = safeText(document.getElementById("hireScoreReplyToInput")?.value).trim() || "recruiter@email.com"
let preview = document.getElementById("hireScoreReplyPreview")
if(preview) preview.innerText = value
}

function saveHireScoreSender(makeActive){
let replyTo = safeText(document.getElementById("hireScoreReplyToInput")?.value).trim()
let senderName = safeText(document.getElementById("hireScoreDisplayNameInput")?.value).trim()
if(!replyTo || !replyTo.includes("@")){
    alert("Please enter a valid reply-to email.")
    document.getElementById("hireScoreReplyToInput")?.focus()
    return
}
writeOutreachSenderConfig({
    mode: "hirescore",
    active: makeActive || readOutreachSenderConfig().mode === "hirescore",
    from_email: HIRE_SCORE_DEFAULT_FROM_EMAIL,
    from_name: HIRE_SCORE_DEFAULT_FROM_NAME,
    reply_to: replyTo,
    sender_name: senderName
})
if(makeActive) removeSenderSetupModal()
}

function openOwnDomainSenderModal(){
let config = readOutreachSenderConfig()
let domain = config.mode === "own_domain" ? safeText(config.domain).trim() : ""
let fromEmail = config.mode === "own_domain" ? safeText(config.from_email).trim() : ""
let senderName = config.mode === "own_domain" ? safeText(config.sender_name || config.from_name).trim() : ""
let records = Array.isArray(config.records) ? config.records : []
let status = config.mode === "own_domain" ? (config.verification_status || "pending") : "pending"
senderModalShell(
    "Connect Your Own Sending Domain",
    "Send emails from your company domain. Add the DNS records below in your domain provider to verify ownership and improve deliverability.",
    `
<div class="ats-sender-form-grid">
<label class="ats-sender-field"><span>Domain</span><input id="ownDomainInput" type="text" value="${safeHtml(domain)}" placeholder="abcagency.com"></label>
<label class="ats-sender-field"><span>From email</span><input id="ownDomainFromInput" type="email" value="${safeHtml(fromEmail)}" placeholder="hr@abcagency.com"></label>
<label class="ats-sender-field"><span>Sender name</span><input id="ownDomainNameInput" type="text" value="${safeHtml(senderName)}" placeholder="ABC Recruitment"></label>
</div>
<div class="ats-sender-preview-box" id="ownDomainPreview">
<div><span>From</span><strong>${safeHtml(senderName || "ABC Recruitment")} &lt;${safeHtml(fromEmail || "hr@abcagency.com")}&gt;</strong></div>
<div><span>Reply-To</span><strong>${safeHtml(fromEmail || "hr@abcagency.com")}</strong></div>
</div>
<div class="ats-sender-actions">
<button type="button" class="ats-gmail-connect-btn" onclick="generateOwnDomainDnsRecords()">Generate DNS Records</button>
</div>
<div id="ownDomainDnsPanel">${records.length ? ownDomainDnsTableHtml(records, status) : ""}</div>`
)
}

function collectOwnDomainForm(){
let domain = normalizeSenderDomain(document.getElementById("ownDomainInput")?.value)
let fromEmail = safeText(document.getElementById("ownDomainFromInput")?.value).trim().toLowerCase()
let senderName = safeText(document.getElementById("ownDomainNameInput")?.value).trim()
if(!domain){
    alert("Please enter your sending domain, for example abcagency.com.")
    document.getElementById("ownDomainInput")?.focus()
    return null
}
if(!fromEmail || !fromEmail.includes("@")){
    alert("Please enter a valid from email, for example hr@abcagency.com.")
    document.getElementById("ownDomainFromInput")?.focus()
    return null
}
if(domainFromEmail(fromEmail) !== domain){
    alert("From email domain must match the entered domain. Example: domain abcagency.com and from email hr@abcagency.com.")
    document.getElementById("ownDomainFromInput")?.focus()
    return null
}
return { domain, from_email: fromEmail, sender_name: senderName || fromEmail.split("@")[0] }
}

function fallbackDnsRecords(domain){
let clean = normalizeSenderDomain(domain)
return [
    { type: "TXT", host: "@", value: "brevo-code:pending-" + clean, ttl: "3600", status: "pending", label: "Brevo code TXT" },
    { type: "CNAME", host: "brevo1._domainkey", value: "brevo1.domainkey.brevo.com", ttl: "3600", status: "pending", label: "DKIM CNAME" },
    { type: "CNAME", host: "brevo2._domainkey", value: "brevo2.domainkey.brevo.com", ttl: "3600", status: "pending", label: "DKIM CNAME" },
    { type: "TXT", host: "_dmarc", value: "v=DMARC1; p=none", ttl: "3600", status: "pending", label: "DMARC TXT" }
]
}

async function generateOwnDomainDnsRecords(){
let form = collectOwnDomainForm()
if(!form) return
let button = typeof event !== "undefined" ? event.target : null
setButtonLoading(button, true, "Generating...")
let payload = { ...form }
try{
    let res = await fetch(API + "/sender-domains/dns-records", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload)
    })
    let data = res.ok ? await res.json() : {}
    let records = Array.isArray(data.records) && data.records.length ? data.records : fallbackDnsRecords(form.domain)
    let status = data.verification_status || "pending"
    ownDomainDraft = { mode: "own_domain", active: false, ...form, from_name: form.sender_name, records, verification_status: status }
    document.getElementById("ownDomainDnsPanel").innerHTML = ownDomainDnsTableHtml(records, status)
}catch(e){
    let records = fallbackDnsRecords(form.domain)
    ownDomainDraft = { mode: "own_domain", active: false, ...form, from_name: form.sender_name, records, verification_status: "pending" }
    document.getElementById("ownDomainDnsPanel").innerHTML = ownDomainDnsTableHtml(records, "pending")
}finally{
    setButtonLoading(button, false)
}
}

function dnsStatusBadge(status){
let clean = safeText(status || "pending").toLowerCase()
let label = clean === "verified" ? "Verified" : clean === "failed" ? "Failed" : "Pending"
return `<span class="ats-dns-status is-${safeHtml(clean)}">${label}</span>`
}

function ownDomainDnsTableHtml(records, verificationStatus){
let rows = records.map((record, index) => {
    let host = record.host || record.name || record.hostname || ""
    let value = record.value || record.content || record.record_value || ""
    let status = record.status || verificationStatus || "pending"
    return `<tr>
<td>${safeHtml(record.type || "")}</td>
<td><strong>${safeHtml(host)}</strong><small>${safeHtml(record.label || "")}</small></td>
<td>${safeHtml(value)}</td>
<td>${safeHtml(record.ttl || "3600")}</td>
<td>${dnsStatusBadge(status)}</td>
<td><button type="button" onclick="copyDnsPart(${index}, 'host')">Copy Host</button><button type="button" onclick="copyDnsPart(${index}, 'value')">Copy Value</button></td>
</tr>`
}).join("")
return `
<div class="ats-sender-warning">Add these records in your own domain DNS provider, not in HireScore AI DNS.</div>
<div class="ats-sender-warning is-danger">Do not change MX records. MX records control email receiving and changing them can break your mailbox.</div>
<p class="ats-sender-helper">If your domain uses Cloudflare, add these records in Cloudflare DNS. If your domain uses GoDaddy, Namecheap, Hostinger, or another provider, add them there.</p>
<div class="ats-dns-table-wrap">
<table class="ats-dns-table">
<thead><tr><th>Type</th><th>Name / Host</th><th>Value / Content</th><th>TTL</th><th>Status</th><th>Action</th></tr></thead>
<tbody>${rows}</tbody>
</table>
</div>
${verificationStatus === "verified" ? `<div class="ats-sender-success">Domain verified. You can now send emails from this domain.</div>` : ""}
<div class="ats-sender-actions">
<button type="button" class="ats-gmail-connect-btn is-secondary" onclick="checkOwnDomainVerification()">Check Verification Status</button>
<button type="button" class="ats-gmail-connect-btn" ${verificationStatus === "verified" ? "" : "disabled"} onclick="activateOwnDomainSender()">Set as Active Sender</button>
</div>`
}

function copyDnsPart(index, field){
let record = (ownDomainDraft?.records || readOutreachSenderConfig().records || [])[index]
if(!record) return
let value = field === "host" ? (record.host || record.name || record.hostname || "") : (record.value || record.content || record.record_value || "")
if(navigator.clipboard?.writeText){
    navigator.clipboard.writeText(value)
}else{
    prompt("Copy value", value)
}
}

async function checkOwnDomainVerification(){
let form = collectOwnDomainForm()
if(!form) return
let button = typeof event !== "undefined" ? event.target : null
setButtonLoading(button, true, "Checking...")
let draft = ownDomainDraft || readOutreachSenderConfig()
try{
    let res = await fetch(API + "/sender-domains/verification-status", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ domain: form.domain, from_email: form.from_email })
    })
    let data = res.ok ? await res.json() : {}
    let status = data.verification_status || data.status || "pending"
    let records = Array.isArray(data.records) && data.records.length ? data.records : (draft.records || fallbackDnsRecords(form.domain))
    ownDomainDraft = { mode: "own_domain", active: false, ...form, from_name: form.sender_name, records, verification_status: status }
    document.getElementById("ownDomainDnsPanel").innerHTML = ownDomainDnsTableHtml(records, status)
}catch(e){
    alert("Verification is still pending. Please confirm the DNS records are saved with your DNS provider.")
}finally{
    setButtonLoading(button, false)
}
}

function activateOwnDomainSender(){
let config = ownDomainDraft || readOutreachSenderConfig()
if(config.verification_status !== "verified"){
    alert("Your sending domain is not verified yet. Please add the DNS records or use HireScore AI sender.")
    return
}
writeOutreachSenderConfig({ ...config, active: true, reply_to: config.from_email })
removeSenderSetupModal()
}

function openReplySyncModal(){
let email = getReplySyncEmail()
senderModalShell(
    "Connect Inbox for Reply Sync",
    "Connect Gmail/Workspace or Outlook to sync candidate replies. This does not change your sending domain.",
    `
<div class="ats-reply-sync-options">
<button type="button" class="ats-gmail-connect-btn" onclick="connectGmailForOutreach()">Google / Workspace OAuth</button>
<button type="button" class="ats-gmail-connect-btn is-secondary" disabled>Outlook/Microsoft OAuth if available</button>
</div>
<p class="ats-sender-helper">Sending uses HireScore AI sender or a verified own-domain sender. Reply sync connects your inbox so candidate replies can be tracked.</p>
<label class="ats-sender-field">
<span>Inbox email for reply sync</span>
<input id="outreachSenderEmail" type="email" value="${safeHtml(email)}" placeholder="recruiter@email.com" oninput="saveOutreachSenderEmail()" onchange="saveOutreachSenderEmail()">
</label>`
)
}

function setFieldIfBlank(id, value){
let el = document.getElementById(id)
let clean = safeText(value).trim()
if(!el || !clean) return
if(!safeText(el.value).trim()){
el.value = clean
}
}

function setSelectIfBlank(id, value){
let el = document.getElementById(id)
let clean = safeText(value).trim()
if(!el || !clean || safeText(el.value).trim()) return
let match = [...el.options].find(option => option.value.toLowerCase() === clean.toLowerCase() || option.text.toLowerCase() === clean.toLowerCase())
if(match){
el.value = match.value
}
}

function applyJDAutofillFields(fields){
fields = fields || {}
setFieldIfBlank("jobTitle", fields.job_title)
setFieldIfBlank("department", fields.department)
setFieldIfBlank("location", fields.location)
setSelectIfBlank("workMode", fields.work_mode)
setSelectIfBlank("jobType", fields.job_type)
setFieldIfBlank("experience", fields.experience_required)
setFieldIfBlank("salary", fields.salary_range)
}

function jdValueAfterLabel(text, labels){
let labelPattern = labels.map(label => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")
let stopLabels = [
"job title","role","position","department","location","job location","experience","employment type","job type","work mode","salary","ctc","compensation","about the role","key responsibilities","responsibilities","requirements","skills","qualification","qualifications"
].join("|")
let regex = new RegExp(`(?:${labelPattern})\\s*[:\\-]\\s*([\\s\\S]*?)(?=\\s+(?:${stopLabels})\\s*[:\\-]|\\n|$)`, "i")
let match = regex.exec(text || "")
return match ? safeText(match[1]).replace(/\s+/g, " ").trim() : ""
}

function normalizeAutofillJobType(value){
let text = safeText(value).toLowerCase()
if(/intern/.test(text)) return "Internship"
if(/contract/.test(text)) return "Contract"
if(/part\s*-?\s*time/.test(text)) return "Part Time"
if(/full\s*-?\s*time|permanent/.test(text)) return "Full Time"
return value
}

function inferAutofillWorkMode(text){
let value = safeText(text)
if(/\bhybrid\b/i.test(value)) return "Hybrid"
if(/\bremote\b|work\s+from\s+home|\bwfh\b/i.test(value)) return "Remote"
if(/\bonsite\b|on-site|work\s+from\s+office|\bwfo\b/i.test(value)) return "Onsite"
return ""
}

function localJDAutofillFields(text){
let location = jdValueAfterLabel(text, ["Location", "Job Location"])
let workMode = jdValueAfterLabel(text, ["Work Mode"]) || inferAutofillWorkMode(location || text)
if(location && workMode){
let modeRegex = new RegExp(`\\s*/?\\s*${workMode}\\s*$`, "i")
location = location.replace(modeRegex, "").trim()
}
return {
job_title: jdValueAfterLabel(text, ["Job Title", "Role", "Position"]),
department: jdValueAfterLabel(text, ["Department", "Team", "Function"]),
location,
work_mode: workMode,
experience_required: jdValueAfterLabel(text, ["Experience", "Exp"]),
job_type: normalizeAutofillJobType(jdValueAfterLabel(text, ["Employment Type", "Job Type"])),
salary_range: jdValueAfterLabel(text, ["Salary", "CTC", "Compensation", "Package"])
}
}

async function uploadJDFile(){
let input = document.getElementById("jdFileUpload")
let status = document.getElementById("jdUploadStatus")
let jdText = document.getElementById("jdText")

if(!input || !input.files || !input.files.length){
if(status) status.textContent = "Select a JD file first"
return
}

let formData = new FormData()
formData.append("file", input.files[0])

if(status) status.textContent = "Reading JD..."

try{
let headers = {}
let token = localStorage.getItem("token")
if(token) headers.Authorization = "Bearer " + token

let res = await fetch(API + "/parse-jd-file", {
method:"POST",
headers,
body:formData
})
let data = await res.json()

if(!res.ok){
if(status) status.textContent = data.detail || "Could not parse JD"
return
}

if(jdText && data.jd_text){
jdText.value = data.jd_text
}

applyJDAutofillFields(data.fields)

if(status) status.textContent = "JD uploaded and fields filled"
}catch(error){
if(status) status.textContent = "Upload failed"
}
}

async function parsePastedJDForAutofill(){
let jdText = document.getElementById("jdText")
let status = document.getElementById("jdUploadStatus")
let text = safeText(jdText?.value).trim()

if(text.length < 120 || text === lastParsedJDText) return
lastParsedJDText = text
applyJDAutofillFields(localJDAutofillFields(text))
if(status) status.textContent = "Reading pasted JD..."

try{
let res = await fetch(API + "/parse-jd-text", {
method:"POST",
headers:authHeaders(),
body:JSON.stringify({ jd_text:text })
})
let data = await res.json()
if(!res.ok){
if(status) status.textContent = ""
return
}
applyJDAutofillFields(data.fields)
if(status) status.textContent = "JD details filled"
setTimeout(()=>{ if(status && status.textContent === "JD details filled") status.textContent = "" }, 2500)
}catch(error){
if(status) status.textContent = ""
}
}

function bindJDAutofill(){
let jdText = document.getElementById("jdText")
if(!jdText || jdText.dataset.autofillBound === "true") return
jdText.dataset.autofillBound = "true"
jdText.addEventListener("input", () => {
clearTimeout(jdAutofillTimer)
jdAutofillTimer = setTimeout(parsePastedJDForAutofill, 900)
})
jdText.addEventListener("paste", () => {
clearTimeout(jdAutofillTimer)
jdAutofillTimer = setTimeout(parsePastedJDForAutofill, 300)
})
}

function currentJobDraft(){
let jdText = safeText(document.getElementById("jdText")?.value).trim()
let title = safeText(document.getElementById("jobTitle")?.value).trim() || "Open Role"
let company = safeText(document.getElementById("company")?.value).trim() || "Company"
let location = safeText(document.getElementById("location")?.value).trim()
let workMode = safeText(document.getElementById("workMode")?.value).trim()
let experience = safeText(document.getElementById("experience")?.value).trim()
let salary = safeText(document.getElementById("salary")?.value).trim()
let jobType = safeText(document.getElementById("jobType")?.value).trim()
let skills = normalizeScreeningSkills([], jdText).slice(0, 8).join(", ")

return { title, company, location, workMode, experience, salary, jobType, skills, jdText }
}

function cleanPostLines(lines){
return lines.filter(line => line !== null && line !== undefined && String(line).trim() !== "").join("\n")
}

function generatedApplyPlaceholder(source){
return `Apply link will be generated after creating the job (${source} tracking link).`
}

function buildJobPlatformPosts(){
let job = currentJobDraft()
let locationLine = [job.location, job.workMode].filter(Boolean).join(" / ")
let hashtagTitle = job.title.replace(/[^a-z0-9]+/gi, "")
let shortSkills = job.skills || "Relevant role skills"

let linkedin = cleanPostLines([
`Hiring: ${job.title}`,
`Company: ${job.company}`,
locationLine ? `Location: ${locationLine}` : "",
job.experience ? `Experience: ${job.experience}` : "",
job.salary ? `Salary: ${job.salary}` : "",
job.jobType ? `Employment Type: ${job.jobType}` : "",
`Skills: ${shortSkills}`,
"",
"Apply here:",
generatedApplyPlaceholder("LinkedIn"),
"",
`#Hiring #${hashtagTitle || "Jobs"} #Jobs #Recruitment #CareerOpportunity`
])

let whatsapp = cleanPostLines([
`Hiring: ${job.title}`,
job.company ? `Company: ${job.company}` : "",
locationLine ? `Location: ${locationLine}` : "",
job.experience ? `Experience: ${job.experience}` : "",
`Skills: ${shortSkills}`,
"",
"Apply here:",
generatedApplyPlaceholder("WhatsApp"),
"",
"Please share with relevant candidates."
])

let naukri = cleanPostLines([
`Job Title: ${job.title}`,
`Company: ${job.company}`,
locationLine ? `Location: ${locationLine}` : "",
job.experience ? `Experience: ${job.experience}` : "",
job.salary ? `Salary: ${job.salary}` : "",
job.jobType ? `Employment Type: ${job.jobType}` : "",
`Key Skills: ${shortSkills}`,
"",
"Naukri External Apply URL:",
generatedApplyPlaceholder("Naukri"),
"",
"If your Naukri recruiter panel supports Company URL / External Apply URL / Apply URL / Redirect URL, paste the generated Naukri tracking link there.",
"",
"Fallback JD text:",
"To apply directly, submit your resume using the generated Naukri tracking link after creating this job.",
"",
job.jdText ? `JD Summary:\n${shortText(job.jdText, 900)}` : ""
])

let generic = cleanPostLines([
`${job.title} - ${job.company}`,
locationLine ? `Location: ${locationLine}` : "",
job.experience ? `Experience: ${job.experience}` : "",
job.salary ? `Salary: ${job.salary}` : "",
job.jobType ? `Job Type: ${job.jobType}` : "",
`Required Skills: ${shortSkills}`,
"",
job.jdText ? shortText(job.jdText, 1200) : "Add the complete job description here.",
"",
"How to apply:",
generatedApplyPlaceholder("Website/Direct")
])

return [
{ key:"linkedinDraft", label:"LinkedIn Social Post", value:linkedin },
{ key:"whatsappDraft", label:"WhatsApp Forward Message", value:whatsapp },
{ key:"naukriDraft", label:"Naukri Posting Text", value:naukri },
{ key:"genericDraft", label:"Other Job Platforms", value:generic }
]
}

function jobPostDraftFromJob(job){
let title = safeText(job?.job_title || "Open Role").trim()
let company = safeText(job?.company_name || "Company").trim()
let location = safeText(job?.location).trim()
let workMode = safeText(job?.work_mode).trim()
let experience = safeText(job?.experience_required).trim()
let salary = safeText(job?.salary_range).trim()
let jobType = safeText(job?.job_type).trim()
let jdText = safeText(job?.jd_text).trim()
let skills = safeText(job?.required_skills).trim() || normalizeScreeningSkills([], jdText).slice(0, 8).join(", ")
let applyLinks = job?.apply_links || {}
return { title, company, location, workMode, experience, salary, jobType, skills, jdText, applyLinks }
}

function buildDashboardJobPosts(job){
let draft = jobPostDraftFromJob(job)
let locationLine = [draft.location, draft.workMode].filter(Boolean).join(" / ")
let hashtagTitle = draft.title.replace(/[^a-z0-9]+/gi, "") || "Jobs"
let posts = job?.generated_posts || {}
let mainLink = draft.applyLinks.main || draft.applyLinks.direct || job?.apply_link || `apply.html?job_id=${encodeURIComponent(job?.id || job?.job_id || "")}`
let linkedinLink = draft.applyLinks.linkedin || mainLink
let whatsappLink = draft.applyLinks.whatsapp || mainLink
let naukriLink = draft.applyLinks.naukri || mainLink
let genericLink = draft.applyLinks.website || draft.applyLinks.direct || mainLink
let skills = draft.skills || "Relevant role skills"

let linkedin = posts.linkedin || cleanPostLines([
`Hiring: ${draft.title}`,
`Company: ${draft.company}`,
locationLine ? `Location: ${locationLine}` : "",
draft.experience ? `Experience: ${draft.experience}` : "",
draft.salary ? `Salary: ${draft.salary}` : "",
`Skills: ${skills}`,
"",
"Apply here:",
linkedinLink,
"",
`#Hiring #${hashtagTitle} #Jobs #Recruitment #CareerOpportunity`
])

let whatsapp = posts.whatsapp || cleanPostLines([
`Hiring: ${draft.title}`,
locationLine ? `Location: ${locationLine}` : "",
draft.experience ? `Experience: ${draft.experience}` : "",
`Skills: ${skills}`,
"",
"Apply here:",
whatsappLink,
"",
"Please share with relevant candidates."
])

let naukri = posts.naukri || cleanPostLines([
"Naukri External Apply URL:",
naukriLink,
"",
"If your Naukri recruiter panel supports Company URL / External Apply URL / Apply URL / Redirect URL, paste the above link there.",
"",
"Fallback JD text:",
"To apply directly, submit your resume here:",
naukriLink,
"",
`${draft.title} - ${draft.company}`,
locationLine ? `Location: ${locationLine}` : "",
draft.experience ? `Experience: ${draft.experience}` : "",
draft.salary ? `Salary: ${draft.salary}` : "",
`Key Skills: ${skills}`,
draft.jdText ? `\nJD Summary:\n${shortText(draft.jdText, 900)}` : ""
])

let generic = posts.generic || cleanPostLines([
`${draft.title} - ${draft.company}`,
locationLine ? `Location: ${locationLine}` : "",
draft.experience ? `Experience: ${draft.experience}` : "",
draft.salary ? `Salary: ${draft.salary}` : "",
draft.jobType ? `Job Type: ${draft.jobType}` : "",
`Required Skills: ${skills}`,
"",
draft.jdText ? shortText(draft.jdText, 1200) : "Full job description available on request.",
"",
"Apply here:",
genericLink
])

return [
{ key:`jobLinkedinPost`, label:"LinkedIn Post", value:linkedin, platform:"linkedin", url:"https://www.linkedin.com/feed/" },
{ key:`jobWhatsappPost`, label:"WhatsApp Message", value:whatsapp, platform:"whatsapp", url:`https://wa.me/?text=${encodeURIComponent(whatsapp)}` },
{ key:`jobNaukriPost`, label:"Naukri Text", value:naukri, platform:"naukri", url:"https://recruit.naukri.com/" },
{ key:`jobGenericPost`, label:"Other Job Platforms", value:generic, platform:"generic", url:genericLink }
]
}

function renderJobPostLoadingCards(){
let cards = [
["linkedin", "LinkedIn Post"],
["whatsapp", "WhatsApp Message"],
["naukri", "Naukri Text"],
["generic", "Other Job Platforms"]
]
return cards.map(([platform, label]) => `
<article class="ats-generated-post-card ats-post-platform-${platform} ats-post-loading-card">
<div class="ats-generated-post-head">
<strong>${label}</strong>
<div><span>AI writing...</span></div>
</div>
<div class="ats-post-loading-lines">
<i></i><i></i><i></i><i></i><i></i>
</div>
</article>
`).join("")
}

async function copyGeneratedPost(key){
let textarea = document.getElementById(key)
let feedback = document.getElementById(key + "Feedback")
let value = textarea?.value || ""
let ok = value ? await copyTextValue(value) : false
if(feedback){
feedback.textContent = ok ? "Copied" : "Failed to copy"
setTimeout(()=>{ feedback.textContent = "" }, 1800)
}
}

function generateJobPlatformPosts(){
let output = document.getElementById("jobPostGeneratorOutput")
if(!output) return

let posts = buildJobPlatformPosts()
output.innerHTML = posts.map(post => `
<article class="ats-generated-post-card ats-post-platform-${safeHtml(post.platform || "generic")}">
<div class="ats-generated-post-head">
<strong>${safeHtml(post.label)}</strong>
<div>
<span id="${safeHtml(post.key)}Feedback"></span>
<button type="button" onclick="copyGeneratedPost('${safeJs(post.key)}')">Copy</button>
</div>
</div>
<textarea id="${safeHtml(post.key)}" readonly>${safeHtml(post.value)}</textarea>
</article>
`).join("")
}

function renderDashboardJobPostCard(post){
let openLabel = post.platform === "generic" ? "Open Apply Link" : "Open Platform"
return `
<article class="ats-generated-post-card ats-post-platform-${safeHtml(post.platform || "generic")}">
<div class="ats-generated-post-head">
<strong>${safeHtml(post.label)}</strong>
<div>
<span id="${safeHtml(post.key)}Feedback"></span>
<button type="button" onclick="copyGeneratedPost('${safeJs(post.key)}')">Copy</button>
<button type="button" onclick="window.open('${safeJs(post.url)}','_blank')">${openLabel}</button>
</div>
</div>
<textarea id="${safeHtml(post.key)}" readonly>${safeHtml(post.value)}</textarea>
</article>
`
}

async function openJobPostKit(jobId){
let job = dashboardJobs.find(item => String(item.id || item.job_id) === String(jobId))
if(!job){
alert("Job data not found. Refresh dashboard and try again.")
return
}
let title = document.getElementById("jobPostPageTitle")
let subtitle = document.getElementById("jobPostPageSubtitle")
let body = document.getElementById("jobPostPageBody")
if(!body) return

if(title) title.textContent = `${job.job_title || "Job"} - Posts`
if(subtitle) subtitle.textContent = `${job.company_name || "Company"} | AI is writing platform-specific posts.`
body.innerHTML = renderJobPostLoadingCards()
showPage("jobPosts")

try{
let res = await fetch(API + "/jobs/" + encodeURIComponent(job.id || job.job_id) + "/ai-posts", {
method:"POST",
headers:authHeaders()
})
let data = await res.json().catch(()=>({}))
if(!res.ok){
throw new Error(data.detail || data.error || "AI post generation failed")
}

let enrichedJob = {
...job,
apply_links:data.apply_links || job.apply_links || {},
generated_posts:data.generated_posts || job.generated_posts || {}
}
let dashboardIndex = dashboardJobs.findIndex(item => String(item.id || item.job_id) === String(jobId))
if(dashboardIndex >= 0){
dashboardJobs[dashboardIndex] = {...dashboardJobs[dashboardIndex], ...enrichedJob}
}
if(subtitle){
subtitle.textContent = data.generated
? `${enrichedJob.company_name || "Company"} | AI-written platform posts are ready to copy and publish.`
: `${enrichedJob.company_name || "Company"} | AI unavailable, showing polished fallback posts.`
}
body.innerHTML = buildDashboardJobPosts(enrichedJob).map(renderDashboardJobPostCard).join("")
}catch(error){
if(subtitle) subtitle.textContent = `${job.company_name || "Company"} | AI post generation failed, showing fallback posts.`
body.innerHTML = `
<div class="ats-post-alert">AI post generation failed. Fallback platform posts are shown below.</div>
${buildDashboardJobPosts(job).map(renderDashboardJobPostCard).join("")}
`
}
}

function closeJobPostModal(){
document.getElementById("jobPostModal")?.classList.add("hidden")
}
// ---------------- CREATE JOB ----------------

async function createJob(event){

if(event) event.preventDefault()

let jobTitle=document.getElementById("jobTitle").value
let company=document.getElementById("company").value
let department=document.getElementById("department").value
let location=document.getElementById("location").value
let workMode=document.getElementById("workMode").value
let jobType=document.getElementById("jobType").value
let experience=document.getElementById("experience").value
let salary=document.getElementById("salary").value
let hiringManager=document.getElementById("hiringManager").value
let deadline=document.getElementById("deadline").value
let jd=document.getElementById("jdText").value
let publicApplyEnabled=document.getElementById("publicApplyEnabled")?.checked ?? true
let sourceTrackingEnabled=document.getElementById("sourceTrackingEnabled")?.checked ?? true


// BASIC VALIDATION

if(!jobTitle || !company || !location || !jd){

alert("Please fill required fields")

return

}


// API REQUEST

let res=await fetch(API+"/create-job",{

method:"POST",

headers:{"Content-Type":"application/json"},

body:JSON.stringify({

job_title:jobTitle,
company_name:company,
department:department,

location:location,
work_mode:workMode,

job_type:jobType,
salary_range:salary,

experience_required:experience,
application_deadline:deadline,
hiring_manager:hiringManager,

jd_text:jd,
public_apply_enabled:publicApplyEnabled,
source_tracking_enabled:sourceTrackingEnabled

})

})


let data=await res.json()

if(!res.ok || data.error){
alert(data.detail || data.error || "Could not create job")
return
}

// SHOW SUCCESS CARD

showSuccessModal(data)

let jobIdText = document.getElementById("jobIdText")
if(jobIdText) jobIdText.innerText=data.job_id

let applyLinkInput = document.getElementById("applyLinkInput")
if(applyLinkInput) applyLinkInput.value=data.apply_link

let openJobBtn = document.getElementById("openJobBtn")
if(openJobBtn) openJobBtn.href=data.apply_link

}

// ---------------- LOAD JOB CARDS ----------------

function createRecruiterJobCard(job){

let jobId = job.id || job.job_id
let title = safeHtml(job.job_title || "Untitled Job")
let company = safeHtml(job.company_name || "Company not specified")
let location = safeHtml(job.location || "N/A")
let salary = safeHtml(job.salary_range || "Not specified")
let jobType = safeHtml(job.job_type || "N/A")
let description = safeHtml(job.jd_text ? shortText(job.jd_text, 150) : "No description added yet.")
let applicants = job.total_applicants || 0
let topScore = job.top_score || 0

return `

<article class="ats-recruiter-job-card">
<div class="ats-recruiter-job-top">
<span class="ats-recruiter-job-icon">JD</span>
<span class="ats-recruiter-job-status">Active</span>
</div>

<div class="ats-recruiter-job-body">
<h3 title="${title}">${title}</h3>
<p>${company}</p>
</div>

<div class="ats-recruiter-job-meta">
<span><strong>Location</strong>${location}</span>
<span><strong>Salary</strong>${salary}</span>
<span><strong>Type</strong>${jobType}</span>
</div>

<p class="ats-recruiter-job-desc">${description}</p>

<button
class="ats-recruiter-result-btn"
onclick="openJobResult('${safeJs(jobId)}','${safeJs(job.job_title || "Untitled Job")}')">
View Results
</button>

<div class="ats-recruiter-job-footer">
<span>Applicants <strong>${applicants}</strong></span>
<span>Top Score <strong>${topScore}</strong></span>
</div>
</article>

`
}

function updateRecruiterSummary(jobs){
jobs = Array.isArray(jobs) ? jobs : []
let activeJobs = jobs.filter(job => job.is_active === true)
let applicants = activeJobs.reduce((sum, job) => sum + (job.total_applicants || 0), 0)
let bestScore = activeJobs.reduce((max, job) => Math.max(max, job.top_score || 0), 0)

let activeEl = document.getElementById("recruiterActiveRoles")
let applicantsEl = document.getElementById("recruiterTotalApplicants")
let bestEl = document.getElementById("recruiterBestScore")

if(activeEl) activeEl.innerText = activeJobs.length
if(applicantsEl) applicantsEl.innerText = applicants
if(bestEl) bestEl.innerText = bestScore
}

async function loadJobs(){

let res = await fetch(API+"/jobs", {
    headers: authHeaders()
})
let jobs = await res.json()
updateRecruiterSummary(jobs)


let container = document.getElementById("jobCards")
if(!container) return
container.style.display="grid"

container.innerHTML=""

jobs
.filter(job => job.is_active === true)
.slice(0,3)
.forEach(job=>{

container.innerHTML += createRecruiterJobCard(job)

}   ) 

}

// ---------------- OPEN JOB RESULT PAGE ----------------
// ---------------- OPEN JOB RESULT PAGE ----------------

function openJobResult(jobId, jobTitle){

showPage("jobResult")
window.currentJobId = jobId
window.currentJobTitle = jobTitle

let title = document.getElementById("jobResultTitle")

if(title){
title.innerText = jobTitle + " Result"
}

loadResults(jobId)

}


// ---------------- LOAD RESULTS ----------------


async function loadResults(jobId){

if(!jobId){
jobId=document.getElementById("jobIdResults").value
}

if(!jobId){
alert("Enter Job ID")
return
}

let res = await fetch(API+"/results/"+jobId)
let data = await res.json()

let table=document.getElementById("resultsTable")
if(!table) return

table.innerHTML=""

let results = Array.isArray(data) ? data : data.results || []

// * YAHI ADD KARNA HAI (START)

let jdSkills = []

try{
    let jobRes = await fetch(API + "/jobs", {
    headers: {
        "Authorization": "Bearer " + localStorage.getItem("token")
    }
})
    let jobs = await jobRes.json()

    let currentJob = Array.isArray(jobs)
        ? jobs.find(j => String(j.id) === String(jobId))
        : null

    if(currentJob){
        jdSkills = normalizeScreeningSkills(
            currentJob.required_skills || [],
            currentJob.jd_text || ""
        )
    }
}catch(err){
}

// fallback (agar JD fail ho)
if(jdSkills.length === 0){

    let jdSignalSources = []
    results.forEach(c=>{
        if(c.matched_skills){
            jdSignalSources.push(c.matched_skills)
        }
        if(c.missing_skills){
            jdSignalSources.push(c.missing_skills)
        }
    })

    jdSkills = normalizeScreeningSkills(jdSignalSources)
}

// global set
currentSkills = jdSkills

renderSkillDropdown()

// * YAHI ADD KARNA HAI (END)

currentResults = results





currentResults = results

let totalApplicants = results.length

let totalScore = 0
let topScore = 0
let shortlistedCount = 0

results.forEach(r=>{
totalScore += r.final_score || 0
topScore = Math.max(topScore, r.final_score || 0)
if(safeText(getDisplayStatus(r)).toLowerCase().includes("shortlist")){
shortlistedCount++
}
})

let avgScore = totalApplicants ? (totalScore / totalApplicants).toFixed(1) : 0

document.getElementById("stat_total_app").innerText = totalApplicants
document.getElementById("stat_avg_score").innerText = avgScore
let topScoreEl = document.getElementById("stat_top_score")
let shortlistedEl = document.getElementById("stat_shortlisted_count")
if(topScoreEl) topScoreEl.innerText = topScore
if(shortlistedEl) shortlistedEl.innerText = shortlistedCount

results.forEach((c,index)=>{
let profileId = registerCandidateProfile(c)
let searchText = candidateResultSearchText(c)

table.innerHTML += `

<tr class="ats-candidate-result-row" data-search-text="${safeHtml(searchText)}" data-score="${safeHtml(c.final_score || 0)}">

<td><span class="ats-rank-badge">#${index+1}</span></td>

<td class="ats-candidate-name-cell">
<button type="button" class="ats-candidate-mini-avatar ats-profile-open-avatar" data-profile-candidate-id="${safeHtml(profileId)}" title="Open candidate profile">${safeHtml(candidateInitials(c.full_name || "Candidate"))}</button>
<span>
${candidateProfileNameButton(c, "ats-candidate-name-link ats-result-name-link")}
<small>${safeHtml(c.email || "No email available")}</small>
</span>
</td>

<td class="hidden">${safeHtml(c.email || "")}</td>
<td class="hidden">${safeHtml(c.phone || "")}</td>

<td>${formatLocation(c.location)}</td>

<td class="hidden">${safeHtml(c.designation || "")}</td>

<td>${formatExperience(c.total_experience_years)}</td>  

<td>${safeHtml(c.last_company_name || "")}</td> 
<td class="hidden">${safeHtml(c.last_working_date || "")}</td>

<td class="hidden">${formatSkills(c.matched_skills)}</td>
<td class="hidden">${formatSkills(cleanedCandidateMissingSkills(c))}</td>

<td class="hidden">${formatPercent(c.skill_match_percent)}</td>

<td class="hidden">${safeHtml(c.industry || "")}</td>
<td class="hidden">${safeHtml(c.domain || "")}</td>
<td class="hidden">${formatEducation(c.education)}</td>

<td><span class="ats-result-status ${getStatusClass(getDisplayStatus(c))}">${getDisplayStatus(c)}</span></td> 
<td><span class="score-badge">${formatScore(c.final_score)}</span></td>
<td class="hidden">
<button onclick="openResumeDownload('${safeJs(c.resume_id)}')"
class="ats-result-row-action ats-result-row-download ${c.resume_available ? "" : "is-unlinked"}"
title="${safeHtml(c.resume_available ? (c.resume_original_filename || "Download resume") : "Try to download stored resume")}">
Resume
</button>
</td>

<td>

<button onclick="openCandidateTracking('${safeJs(c.resume_id)}')"
class="ats-result-row-action ats-result-row-track">
Track
</button>

<button onclick="deleteCandidate('${safeJs(c.resume_id)}')"
class="ats-result-row-action ats-result-row-delete">
Delete
</button>

</td>

</tr>

`
})

}

async function openCandidateTracking(id){
let candidate = currentResults.find(c => c.resume_id === id || c.id === id) || {}
let fallback = {
    id: id,
    job_id: candidate.job_id || window.currentJobId || "",
    name: candidate.full_name || candidate.name || "",
    email: candidate.email || "",
    phone: candidate.phone || "",
    location: candidate.location || "",
    job_title: window.currentJobTitle || "",
    final_score: candidate.final_score ?? "",
    confidence_score: candidate.confidence_score ?? "",
    status: candidate.status || "",
    stage: candidate.stage || "",
    mail_status: candidate.mail_status || "",
    response_status: candidate.response_status || "",
    designation: candidate.designation || "",
    experience: candidate.total_experience_years ?? "",
    matched_skills: candidate.matched_skills || "",
    missing_skills: candidate.missing_skills || ""
}

try{
    sessionStorage.setItem("candidateTrackingFallback", JSON.stringify(fallback))
}catch(err){
}

let trackingUrl = "candidate-tracking.html?candidate_id=" + encodeURIComponent(id)
let trackingWindow = window.open("about:blank", "_blank")
try{
    let res = await fetch(API + "/candidate/tracking-link/" + encodeURIComponent(id), {
        headers: authHeaders()
    })
    if(res.ok){
        let data = await res.json()
        if(data && data.token){
            trackingUrl = "candidate-tracking.html?token=" + encodeURIComponent(data.token)
        }
    }
}catch(err){
}

if(trackingWindow){
    trackingWindow.location.href = trackingUrl
}else{
    window.open(trackingUrl, "_blank")
}

}

async function deleteCandidate(id){
if(!id){
alert("Candidate id missing.")
return
}

if(!confirm("Delete this candidate from active ATS views?")){
return
}

let button = typeof event !== "undefined" ? event.currentTarget : null
setButtonLoading(button, true, "Deleting...")

try{
let res = await fetch(API + "/drop-candidate/" + encodeURIComponent(id), {
method: "POST",
headers: authHeaders()
})

let data = await res.json().catch(()=>({}))
if(!res.ok || data.error){
alert(data.detail || data.error || "Could not delete candidate")
return
}

currentResults = (currentResults || []).filter(candidate => candidate.resume_id !== id && candidate.id !== id)

if(window.currentJobId){
await loadResults(window.currentJobId)
}else{
let row = button ? button.closest("tr") : null
if(row) row.remove()
}

alert(data.message || "Candidate deleted")
}catch(error){
alert("Could not delete candidate")
}finally{
if(button && document.body.contains(button)){
setButtonLoading(button, false)
}
}
}

async function openAllJobsPage(){

showPage("allJobs")

let res = await fetch(API+"/jobs", {
    headers: authHeaders()
})
let jobs = await res.json()

let container=document.getElementById("allJobsContainer")

container.innerHTML=""

jobs.forEach(job=>{

container.innerHTML+=`
<div class="job-card">

<h3>${job.job_title}</h3>

<button onclick="openJobResult('${job.id}','${job.job_title}')">
View Results
</button>

</div>
`

})

}

// ---------------- BULK ANALYZE ----------------

async function analyzeBulkResumes(){

let jd=document.getElementById("bulkJD").value
let files=document.getElementById("bulkResumes").files
let analyzeBtn=document.getElementById("bulkAnalyzeBtn")
let resultBox=document.getElementById("bulkResult")

if(!jd){
alert("Paste JD")
return
}

if(files.length==0){
alert("Upload resumes")
return
}

let progressTimer = startBulkAnalyzeProgress(files.length)

let formData=new FormData()
formData.append("jd_text",jd)

for(let i=0;i<files.length;i++){
formData.append("files",files[i])
}

try{
if(analyzeBtn){
analyzeBtn.disabled = true
analyzeBtn.classList.add("is-loading")
analyzeBtn.innerText = "Analyzing..."
}

let res=await fetch(API+"/bulk-analyze",{
method:"POST",
body:formData
})

if(!res.ok){
throw new Error(await res.text())
}

let data=await res.json()

bulkResults=data.results || []
initializeBulkWorkflowState(bulkResults)
saveBulkSession(jd)

finishBulkAnalyzeProgress(progressTimer, data.total_resumes || bulkResults.length)

renderBulkTable(bulkResults)
renderTop10Candidates()
if(bulkResults.length){
generateBulkAnalytics()
}
renderBulkWorkflowPages()
showBulkSection("candidates")

}catch(error){
if(resultBox){
resultBox.innerHTML = `
<div class="ats-bulk-progress-card is-error">
<strong>Analysis failed</strong>
<span>${safeHtml(error.message || "Could not analyze resumes. Please try again.")}</span>
</div>
`
}
}finally{
clearInterval(progressTimer)
if(analyzeBtn){
analyzeBtn.disabled = false
analyzeBtn.classList.remove("is-loading")
analyzeBtn.innerText = "Analyze Resumes"
}
}

}

// ---------------- BULK TABLE ----------------

function startBulkAnalyzeProgress(fileCount){
let resultBox=document.getElementById("bulkResult")
let startedAt=Date.now()
let steps=[
"Uploading resumes securely",
"Extracting resume text",
"Reading JD with the same matching engine",
"Scoring skills, experience, and semantic fit",
"Building ranked candidate table"
]
let stepIndex=0

if(resultBox){
resultBox.innerHTML = bulkAnalyzeProgressMarkup(steps[stepIndex], 8, fileCount, startedAt)
}

return setInterval(()=>{
stepIndex = Math.min(stepIndex + 1, steps.length - 1)
let percent = Math.min(92, 8 + stepIndex * 20)
if(resultBox){
resultBox.innerHTML = bulkAnalyzeProgressMarkup(steps[stepIndex], percent, fileCount, startedAt)
}
}, 1800)
}

function bulkAnalyzeProgressMarkup(message, percent, fileCount, startedAt){
let seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000))
return `
<div class="ats-bulk-progress-card">
<div class="ats-bulk-progress-head">
<div>
<strong>Analyzing ${safeHtml(fileCount)} resume${fileCount === 1 ? "" : "s"}</strong>
<span>${safeHtml(message)}</span>
</div>
<b>${safeHtml(percent)}%</b>
</div>
<div class="ats-bulk-progress-track"><i style="width:${percent}%"></i></div>
<p>Using the same backend resume matching pipeline as normal job analysis. Elapsed ${safeHtml(seconds)}s.</p>
</div>
`
}

function finishBulkAnalyzeProgress(timer,total){
clearInterval(timer)
let resultBox=document.getElementById("bulkResult")
if(resultBox){
resultBox.innerHTML = `
<div class="ats-bulk-progress-card is-complete">
<div class="ats-bulk-progress-head">
<div>
<strong>Analysis completed</strong>
<span>${safeHtml(total)} resume${total === 1 ? "" : "s"} processed and ranked.</span>
</div>
<b>100%</b>
</div>
<div class="ats-bulk-progress-track"><i style="width:100%"></i></div>
<p>Results are ready below in the independent bulk workflow.</p>
</div>
`
}
}

function initializeBulkWorkflowState(results){
bulkWorkflowState = createEmptyBulkWorkflowState()

(results || []).forEach((candidate,index)=>{
candidate._bulk_id = bulkCandidateId(candidate,index)
candidate._bulk_status = candidate._bulk_status || "Review"
})

updateBulkWorkflowCounts()
}

function bulkSessionTitle(jdText){
let lines = safeText(jdText)
.split(/\r?\n/)
.map(line=>line.trim())
.filter(Boolean)

let titleLine = lines.find(line=>/role|position|title|job/i.test(line)) || lines[0] || "Bulk resume result"
titleLine = titleLine.replace(/^(job\s*)?(role|position|title)\s*[:\-]\s*/i,"")
titleLine = titleLine.replace(/\s+/g," ").trim()
return shortText(titleLine || "Bulk resume result", 58)
}

function readBulkHistory(){
try{
let parsed = JSON.parse(localStorage.getItem(BULK_HISTORY_KEY) || "[]")
return Array.isArray(parsed) ? parsed : []
}catch{
return []
}
}

function writeBulkHistory(history){
try{
localStorage.setItem(BULK_HISTORY_KEY, JSON.stringify((history || []).slice(0,5)))
}catch(error){
}
}

function buildBulkSessionSnapshot(jdText){
return {
id: currentBulkSessionId || "bulk-" + Date.now(),
title: bulkSessionTitle(jdText),
jd_text: safeText(jdText),
created_at: new Date().toISOString(),
total_resumes: bulkResults.length,
results: bulkResults,
workflowState: bulkWorkflowState
}
}

function saveBulkSession(jdText){
if(!bulkResults.length) return null

let session = buildBulkSessionSnapshot(jdText)
currentBulkSessionId = session.id

try{
localStorage.setItem(BULK_ACTIVE_SESSION_KEY, JSON.stringify(session))
let history = readBulkHistory().filter(item=>item && item.id !== session.id)
history.unshift(session)
writeBulkHistory(history)
}catch(error){
}

renderBulkRecentSessions()
renderBulkSessionControls()
return session
}

function persistActiveBulkSession(){
if(!bulkResults.length) return
let jdText = document.getElementById("bulkJD")?.value || ""
saveBulkSession(jdText)
}

function renderBulkSessionControls(){
let dropBtn = document.getElementById("dropBulkSessionBtn")
if(dropBtn) dropBtn.classList.toggle("hidden", !bulkResults.length)
}

function renderBulkRecentSessions(){
let container = document.getElementById("bulkRecentSessions")
if(!container) return

let history = readBulkHistory().slice(0,5)
if(!history.length){
container.innerHTML = ""
return
}

container.innerHTML = `
<div class="ats-bulk-recent-head">
<strong>Last 5 batch results</strong>
<span>Open saved results without re-analyzing resumes.</span>
</div>
<div class="ats-bulk-recent-list">
${history.map(session=>{
let isActive = session.id === currentBulkSessionId
let dateLabel = session.created_at ? new Date(session.created_at).toLocaleString() : "Saved result"
return `
<button type="button" class="${isActive ? "is-active" : ""}" onclick="loadBulkSession('${safeJs(session.id)}')">
<b>For this job: ${safeHtml(session.title || "Bulk result")}</b>
<span>${safeHtml(session.total_resumes || 0)} candidates - ${safeHtml(dateLabel)}</span>
</button>
`
}).join("")}
</div>
`
}

function restoreBulkSession(session, options = {}){
if(!session || !Array.isArray(session.results)) return false

currentBulkSessionId = session.id || "bulk-" + Date.now()
bulkResults = session.results || []
bulkWorkflowState = session.workflowState || createEmptyBulkWorkflowState()

bulkResults.forEach((candidate,index)=>{
candidate._bulk_id = bulkCandidateId(candidate,index)
candidate._bulk_status = candidate._bulk_status || "Review"
})

let jdInput = document.getElementById("bulkJD")
if(jdInput) jdInput.value = session.jd_text || ""

renderBulkTable(bulkResults)
renderTop10Candidates()
if(bulkResults.length) generateBulkAnalytics()
renderBulkWorkflowPages()
finishBulkAnalyzeProgress(null, session.total_resumes || bulkResults.length)
renderBulkRecentSessions()
renderBulkSessionControls()

if(options.activate !== false){
showBulkSection("candidates")
}

return true
}

function restoreBulkSessionFromStorage(){
renderBulkRecentSessions()
renderBulkSessionControls()
if(bulkResults.length) return

try{
let session = JSON.parse(localStorage.getItem(BULK_ACTIVE_SESSION_KEY) || "null")
if(session) restoreBulkSession(session, {activate:false})
}catch(error){
}
}

function loadBulkSession(sessionId){
let session = readBulkHistory().find(item=>item && item.id === sessionId)
if(!session) return
try{
localStorage.setItem(BULK_ACTIVE_SESSION_KEY, JSON.stringify(session))
}catch{}
restoreBulkSession(session)
}

function dropBulkSession(){
if(!bulkResults.length) return
let ok = confirm("Drop this saved bulk batch? This removes it from the current screen and saved last results.")
if(!ok) return

let droppedId = currentBulkSessionId
bulkResults = []
bulkWorkflowState = createEmptyBulkWorkflowState()
currentBulkSessionId = null
destroyCharts()

try{
localStorage.removeItem(BULK_ACTIVE_SESSION_KEY)
writeBulkHistory(readBulkHistory().filter(item=>item && item.id !== droppedId))
}catch{}

let jdInput = document.getElementById("bulkJD")
let fileInput = document.getElementById("bulkResumes")
if(jdInput) jdInput.value = ""
if(fileInput) fileInput.value = ""

let resultBox = document.getElementById("bulkResult")
if(resultBox) resultBox.innerHTML = ""

let bulkTable = document.getElementById("bulkResultsTable")
let topTable = document.getElementById("top10Table")
let analyticsSummary = document.getElementById("bulkAnalyticsSummary")
if(bulkTable) bulkTable.innerHTML = ""
if(topTable) topTable.innerHTML = ""
if(analyticsSummary) analyticsSummary.innerHTML = ""

renderBulkWorkflowPages()
renderBulkRecentSessions()
renderBulkSessionControls()
showBulkSection("candidates")
}

function bulkCandidateId(candidate,index=0){
let stable = candidate?._bulk_id
if(stable) return stable

let seed = [
candidate?.email,
candidate?.phone,
candidate?.full_name,
candidate?.resume_id,
candidate?.id,
index
].filter(Boolean).join("-").toLowerCase()

return "bulk-" + seed.replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")
}

function findBulkCandidate(candidateId){
return bulkResults.find((candidate,index)=>bulkCandidateId(candidate,index) === candidateId)
}

function bulkWorkflowActions(candidate,index){
let candidateId = bulkCandidateId(candidate,index)
let inShortlist = !!bulkWorkflowState.shortlist[candidateId]
let inCommunication = !!bulkWorkflowState.communication[candidateId]
let inInterview = !!bulkWorkflowState.interview[candidateId]
let label = inInterview ? "Interview" : inCommunication ? "Communication" : inShortlist ? "Shortlisted" : "Shortlist"
let className = inInterview ? "is-interview is-done" : inCommunication ? "is-done" : inShortlist ? "is-done" : ""

return `
<div class="ats-bulk-workflow-actions">
<button type="button" onclick="shortlistBulkCandidate('${safeJs(candidateId)}')" class="ats-bulk-mini-btn ${className}">
${label}
</button>
</div>
`
}

function shortlistBulkCandidate(candidateId){
let candidate = findBulkCandidate(candidateId)
if(!candidate) return

bulkWorkflowState.shortlist[candidateId] = bulkWorkflowState.shortlist[candidateId] || {
addedAt: new Date().toISOString(),
status: "Recruiter shortlisted"
}
candidate._bulk_status = "Bulk Shortlisted"
persistActiveBulkSession()
renderBulkWorkflowPages()
renderBulkTable(currentBulkViewResults())
renderTop10Candidates()
showBulkSection("shortlist")
}

function moveBulkCandidateToCommunication(candidateId){
let candidate = findBulkCandidate(candidateId)
if(!candidate) return

bulkWorkflowState.shortlist[candidateId] = bulkWorkflowState.shortlist[candidateId] || {
addedAt: new Date().toISOString(),
status: "Recruiter shortlisted"
}

bulkWorkflowState.communication[candidateId] = {
addedAt: new Date().toISOString(),
status: "Pending response",
response: "Pending"
}
candidate._bulk_status = "Bulk Outreach"
persistActiveBulkSession()
renderBulkWorkflowPages()
renderBulkTable(currentBulkViewResults())
renderTop10Candidates()
showBulkSection("communication")
}

function moveBulkCandidateToInterview(candidateId){
let candidate = findBulkCandidate(candidateId)
if(!candidate) return

bulkWorkflowState.shortlist[candidateId] = bulkWorkflowState.shortlist[candidateId] || {
addedAt: new Date().toISOString(),
status: "Recruiter shortlisted"
}
bulkWorkflowState.communication[candidateId] = bulkWorkflowState.communication[candidateId] || {
addedAt: new Date().toISOString(),
status: "Interested",
response: "Interested"
}

bulkWorkflowState.interview[candidateId] = {
addedAt: new Date().toISOString(),
status: "Ready for interview"
}
candidate._bulk_status = "Bulk Interview"
persistActiveBulkSession()
renderBulkWorkflowPages()
renderBulkTable(currentBulkViewResults())
renderTop10Candidates()
showBulkSection("interview")
}

function currentBulkViewResults(){
let name=document.getElementById("searchName")?.value?.toLowerCase() || ""
let skill=document.getElementById("skillFilter")?.value?.toLowerCase() || ""
let location=document.getElementById("locationFilter")?.value?.toLowerCase() || ""
let education=document.getElementById("educationFilter")?.value?.toLowerCase() || ""
let score=document.getElementById("scoreFilter")?.value || ""

return bulkResults.filter(r=>{
let nameMatch=!name||(r.full_name||"").toLowerCase().includes(name)
let skillMatch=!skill||cleanedCandidateMatchedSkills(r).join(" ").toLowerCase().includes(skill)
let locMatch=!location||(r.location||"").toLowerCase().includes(location)
let eduMatch=!education||safeText(r.education).toLowerCase().includes(education)
let scoreMatch=!score||Number(r.final_score || 0)>=Number(score)
return nameMatch&&skillMatch&&locMatch&&eduMatch&&scoreMatch
})
}

function renderBulkTable(results){

let table = document.getElementById("bulkResultsTable")

if(!table) return

table.innerHTML = ""

results.forEach((r,index)=>{
let profileId = registerCandidateProfile(r)

let row = `

<tr class="border-b hover:bg-gray-50 transition">

<td class="px-4 py-3">${index+1}</td>

<td class="px-4 py-3">
<button type="button" class="ats-candidate-name-link ats-legacy-name-link" data-profile-candidate-id="${safeHtml(profileId)}">${safeHtml(r.full_name || "Candidate")}</button>
</td>

<td class="px-4 py-3">${r.email || ""}</td>

<td class="px-4 py-3 hidden">${r.phone || ""}</td>

<td class="px-4 py-3">${r.location || ""}</td>

<td class="px-4 py-3 hidden">${r.designation || ""}</td>

<td class="px-4 py-3">${r.total_experience_years || 0}</td>

<td class="px-4 py-3 hidden">${r.last_company_name || ""}</td>

<td class="px-4 py-3 hidden">${r.last_working_date || ""}</td>

<td class="px-4 py-3 hidden">${r.matched_skills || ""}</td>

<td class="px-4 py-3 hidden">${safeHtml(cleanedCandidateMissingSkills(r).join(", "))}</td>

<td class="px-4 py-3 hidden">${r.skill_match_percent || 0}</td>

<td class="px-4 py-3 hidden">${r.industry || ""}</td>

<td class="px-4 py-3 hidden">${r.domain || ""}</td>

<td class="px-4 py-3 hidden">${formatEducation(r.education)}</td>

<td class="px-4 py-3 hidden">${getStatus(r.final_score)}</td>

<td class="px-4 py-3 font-semibold text-indigo-600">${r.final_score || 0}</td>
<td class="px-4 py-3">${bulkWorkflowActions(r,index)}</td>

</tr>

`

table.innerHTML += row

})

}

function toggleBulkColumnPanel(){

let panel=document.getElementById("bulkColumnPanel")

panel.style.display =
panel.style.display==="none" ? "block" : "none"

}

function toggleBulkColumn(checkbox){

let col = parseInt(checkbox.dataset.col)

let table = document.getElementById("bulkAnalyzerTable")

if(!table) return

let headers = table.querySelectorAll("thead th")
let rows = table.querySelectorAll("tbody tr")

// HEADER
if(headers[col]){

if(checkbox.checked){
headers[col].classList.remove("hidden")
}else{
headers[col].classList.add("hidden")
}

}

// BODY
rows.forEach(row=>{

let cell = row.children[col]

if(!cell) return

if(checkbox.checked){
cell.classList.remove("hidden")
}else{
cell.classList.add("hidden")
}

})

}

// ---------------- DETAILS TOGGLE ----------------

function toggleDetails(index){

let row=document.getElementById("details-"+index)

if(row.style.display==="none"){
row.style.display="table-row"
}else{
row.style.display="none"
}

}

// ---------------- FILTER ----------------

function applyBulkFilters(){

let name=document.getElementById("searchName").value.toLowerCase()
let skill=document.getElementById("skillFilter").value.toLowerCase()
let location=document.getElementById("locationFilter").value.toLowerCase()
let education=document.getElementById("educationFilter").value.toLowerCase()
let score=document.getElementById("scoreFilter").value

let filtered=bulkResults.filter(r=>{

let nameMatch=!name||(r.full_name||"").toLowerCase().includes(name)
let skillMatch=!skill||cleanedCandidateMatchedSkills(r).join(" ").toLowerCase().includes(skill)
let locMatch=!location||(r.location||"").toLowerCase().includes(location)
let eduMatch=!education||safeText(formatEducation(r.education)).toLowerCase().includes(education)
let scoreMatch=!score||r.final_score>=score

return nameMatch&&skillMatch&&locMatch&&eduMatch&&scoreMatch

})

renderBulkTable(filtered)

}

// ---------------- TOP 10 ----------------

function renderTop10Candidates(){

let top=[...bulkResults]
.sort(compareCandidateRank)
.slice(0,10)

let table=document.getElementById("top10Table")

table.innerHTML=""

top.forEach((c,index)=>{
let profileId = registerCandidateProfile(c)

table.innerHTML+=`

<tr>

<td>${index+1}</td>

<td><button type="button" class="ats-candidate-name-link ats-legacy-name-link" data-profile-candidate-id="${safeHtml(profileId)}">${safeHtml(c.full_name || "Candidate")}</button></td>
<td>${c.email || ""}</td>
<td>${c.phone || ""}</td>
<td>${c.location || ""}</td>

<td>${c.designation || ""}</td>
<td>${c.total_experience_years || 0}</td>

<td>${c.last_company_name || ""}</td>
<td>${c.last_working_date || ""}</td>

<td>${c.matched_skills || ""}</td>
<td>${safeHtml(cleanedCandidateMissingSkills(c).join(", "))}</td>
<td>${c.skill_match_percent || 0}</td>

<td>${c.industry || ""}</td>
<td>${c.domain || ""}</td>
<td>${formatEducation(c.education)}</td>

<td>${c.status || "Review"}</td>
<td>${c.final_score || 0}</td>

<td>

<button onclick="openCandidateAIProfile(${index})"
class="bg-indigo-600 text-white px-3 py-1 rounded text-sm">

AI Explain

</button>

</td>
<td>${bulkWorkflowActions(c,index)}</td>

</tr>

`

})

}
// ---------------- ANALYTICS ----------------

function incrementCount(map, label){
let clean = safeText(label).replace(/\s+/g," ").trim()
if(!clean) return
map[clean] = (map[clean] || 0) + 1
}

function topCountEntries(map, limit=8){
return Object.entries(map)
.sort((a,b)=>b[1]-a[1] || a[0].localeCompare(b[0]))
.slice(0,limit)
}

function compactChartLabel(label, max=28){
let clean = safeText(label).replace(/\s+/g," ").trim()
return clean.length > max ? clean.slice(0,max - 3) + "..." : clean
}

function analyticsEducationLabel(educationValue){
if(!educationValue) return "Not listed"

let edu = educationValue
if(typeof edu === "string"){
try{
edu = JSON.parse(edu)
}catch{
return compactChartLabel(edu.replace(/<[^>]*>/g,""), 34) || "Not listed"
}
}

if(Array.isArray(edu) && edu.length){
let first = edu[0] || {}
let degree = safeText(first.degree || first.course || first.name).trim()
let field = safeText(first.field || first.specialization).trim()
return compactChartLabel([degree, field].filter(Boolean).join(" - ") || "Not listed", 34)
}

if(typeof edu === "object"){
let degree = safeText(edu.degree || edu.course || edu.name).trim()
let field = safeText(edu.field || edu.specialization).trim()
return compactChartLabel([degree, field].filter(Boolean).join(" - ") || "Not listed", 34)
}

return "Not listed"
}

function chartBaseOptions(extra = {}){
return {
responsive: true,
maintainAspectRatio: false,
plugins: {
legend: {
display: extra.legend !== false,
position: "bottom",
labels: {
boxWidth: 10,
boxHeight: 10,
usePointStyle: true,
font: {size: 11, weight: "700"}
}
},
tooltip: {
backgroundColor: "#0f172a",
titleFont: {size: 12, weight: "800"},
bodyFont: {size: 12},
padding: 10
}
},
scales: extra.scales,
indexAxis: extra.indexAxis
}
}

function renderBulkAnalyticsSummary(summary){
let container = document.getElementById("bulkAnalyticsSummary")
if(!container) return

container.innerHTML = `
<article>
<span>Total resumes</span>
<strong>${safeHtml(summary.total)}</strong>
<small>Processed in current batch</small>
</article>
<article>
<span>Average score</span>
<strong>${safeHtml(formatScore(summary.avgScore))}</strong>
<small>Across all candidates</small>
</article>
<article>
<span>Strong profiles</span>
<strong>${safeHtml(summary.strongCount)}</strong>
<small>Score 75 and above</small>
</article>
<article>
<span>Top skill signal</span>
<strong>${safeHtml(summary.topSkill || "Not found")}</strong>
<small>Most common matched skill</small>
</article>
`
}

function generateBulkAnalytics(){

destroyCharts()

let skills={}
let locations={}
let education={}
let scores=[0,0,0,0,0]

let expBuckets={"0-1":0,"1-3":0,"3-5":0,"5+":0}

bulkResults.forEach(r=>{

cleanedCandidateMatchedSkills(r).forEach(skill=>incrementCount(skills, skill))

let loc=r.location||"Unknown"
incrementCount(locations, loc)

incrementCount(education, analyticsEducationLabel(r.education))

let sc=r.final_score||0

if(sc<20)scores[0]++
else if(sc<40)scores[1]++
else if(sc<60)scores[2]++
else if(sc<80)scores[3]++
else scores[4]++

let exp=r.total_experience_years||0

if(exp<=1)expBuckets["0-1"]++
else if(exp<=3)expBuckets["1-3"]++
else if(exp<=5)expBuckets["3-5"]++
else expBuckets["5+"]++

})

let total = bulkResults.length
let avgScore = total ? bulkResults.reduce((sum,item)=>sum + (Number(item.final_score) || 0), 0) / total : 0
let strongCount = bulkResults.filter(item=>(Number(item.final_score) || 0) >= 75).length
let topSkill = topCountEntries(skills, 1)[0]?.[0] || ""
renderBulkAnalyticsSummary({total, avgScore, strongCount, topSkill})

let skillEntries = topCountEntries(skills, 10)
let locationEntries = topCountEntries(locations, 8)
let educationEntries = topCountEntries(education, 7)
let skillCanvas = document.getElementById("bulkSkillChart")
let expCanvas = document.getElementById("bulkExpChart")
let locationCanvas = document.getElementById("bulkLocationChart")
let educationCanvas = document.getElementById("bulkEducationChart")
let scoreCanvas = document.getElementById("bulkScoreChart")

if(skillCanvas){
charts.skills=new Chart(skillCanvas,{
type:"bar",
data:{
labels:skillEntries.map(([label])=>compactChartLabel(label, 24)),
datasets:[{
label:"Candidates",
data:skillEntries.map(([,count])=>count),
backgroundColor:"#2563eb",
borderRadius:8,
barThickness:18
}]
},
options:chartBaseOptions({
legend:false,
indexAxis:"y",
scales:{
x:{beginAtZero:true,ticks:{precision:0},grid:{color:"#e5e7eb"}},
y:{grid:{display:false},ticks:{font:{size:12,weight:"700"}}}
}
})
})
}

if(expCanvas){
charts.exp=new Chart(expCanvas,{
type:"doughnut",
data:{
labels:Object.keys(expBuckets),
datasets:[{
data:Object.values(expBuckets),
backgroundColor:["#38bdf8","#60a5fa","#f59e0b","#10b981"],
borderColor:"#ffffff",
borderWidth:3,
hoverOffset:6
}]
},
options:chartBaseOptions({legend:true})
})
}

if(locationCanvas){
charts.location=new Chart(locationCanvas,{
type:"bar",
data:{
labels:locationEntries.map(([label])=>compactChartLabel(label, 26)),
datasets:[{
label:"Candidates",
data:locationEntries.map(([,count])=>count),
backgroundColor:"#14b8a6",
borderRadius:8,
barThickness:18
}]
},
options:chartBaseOptions({
legend:false,
indexAxis:"y",
scales:{
x:{beginAtZero:true,ticks:{precision:0},grid:{color:"#e5e7eb"}},
y:{grid:{display:false},ticks:{font:{size:12,weight:"700"}}}
}
})
})
}

if(educationCanvas){
charts.education=new Chart(educationCanvas,{
type:"bar",
data:{
labels:educationEntries.map(([label])=>compactChartLabel(label, 24)),
datasets:[{
label:"Candidates",
data:educationEntries.map(([,count])=>count),
backgroundColor:"#8b5cf6",
borderRadius:8,
barThickness:16
}]
},
options:chartBaseOptions({
legend:false,
indexAxis:"y",
scales:{
x:{beginAtZero:true,ticks:{precision:0},grid:{color:"#e5e7eb"}},
y:{grid:{display:false},ticks:{font:{size:11,weight:"700"}}}
}
})
})
}

if(scoreCanvas){
charts.score=new Chart(scoreCanvas,{
type:"bar",
data:{
labels:["0-20","20-40","40-60","60-80","80-100"],
datasets:[{
label:"Candidates",
data:scores,
backgroundColor:["#fca5a5","#fdba74","#fde047","#60a5fa","#34d399"],
borderRadius:10,
barThickness:34
}]
},
options:chartBaseOptions({
legend:false,
scales:{
x:{grid:{display:false},ticks:{font:{size:12,weight:"800"}}},
y:{beginAtZero:true,ticks:{precision:0},grid:{color:"#e5e7eb"}}
}
})
})
}

}

// ---------------- DESTROY OLD CHARTS ----------------

function destroyCharts(){

Object.values(charts).forEach(chart=>{
if(chart) chart.destroy()
})

charts={}

}

// ---------------- BULK SECTION SWITCH ----------------

function showBulkSection(section){

document.getElementById("bulkCandidates").classList.add("hidden")
document.getElementById("bulkTop10").classList.add("hidden")
document.getElementById("bulkAnalytics").classList.add("hidden")
document.getElementById("bulkShortlist")?.classList.add("hidden")
document.getElementById("bulkCommunication")?.classList.add("hidden")
document.getElementById("bulkInterview")?.classList.add("hidden")
document.getElementById("candidateAIProfilePage")?.classList.add("hidden")
document.getElementById("candidateAIBackTop10")?.classList.add("hidden")

if(section==="candidates")
document.getElementById("bulkCandidates").classList.remove("hidden")

if(section==="top10")
document.getElementById("bulkTop10").classList.remove("hidden")

if(section==="analytics"){
if(bulkResults.length) generateBulkAnalytics()
document.getElementById("bulkAnalytics").classList.remove("hidden")
}

if(section==="shortlist"){
renderBulkWorkflowPages()
document.getElementById("bulkShortlist")?.classList.remove("hidden")
}

if(section==="communication"){
renderBulkWorkflowPages()
document.getElementById("bulkCommunication")?.classList.remove("hidden")
}

if(section==="interview"){
renderBulkWorkflowPages()
document.getElementById("bulkInterview")?.classList.remove("hidden")
}

}

function renderBulkWorkflowPages(){
renderBulkWorkflowList("shortlist")
renderBulkWorkflowList("communication")
renderBulkWorkflowList("interview")
updateBulkWorkflowCounts()
}

function renderBulkWorkflowList(type){
let listMap = {
shortlist: "bulkShortlistList",
communication: "bulkCommunicationList",
interview: "bulkInterviewList"
}
let list = document.getElementById(listMap[type])
if(!list) return

let queue = Object.keys(bulkWorkflowState[type] || {})
.map(candidateId => ({candidateId, candidate: findBulkCandidate(candidateId), meta: bulkWorkflowState[type][candidateId]}))
.filter(item => item.candidate)
.sort((a,b)=>compareCandidateRank(a.candidate,b.candidate))

if(type === "shortlist"){
renderBulkShortlistBoard(list, queue)
return
}

if(!queue.length){
list.innerHTML = `
<div class="ats-bulk-empty-workflow">
<strong>No candidates selected yet</strong>
<span>${safeHtml(bulkEmptyWorkflowText(type))}</span>
</div>
`
return
}

list.innerHTML = queue.map((item,index)=>bulkWorkflowCard(item.candidate,item.candidateId,item.meta,type,index)).join("")
}

function renderBulkShortlistBoard(list, queue){
let summary = document.getElementById("bulkShortlistSummary")
let total = queue.length
let avgScore = total
? Math.round(queue.reduce((sum,item)=>sum + candidateRecruiterScore(item.candidate), 0) / total)
: 0
let topCandidate = queue[0]?.candidate
let readyCount = queue.filter(item => !bulkWorkflowState.communication[item.candidateId]).length

if(summary){
summary.innerHTML = `
<article>
<span>Total shortlisted</span>
<strong>${safeHtml(total)}</strong>
</article>
<article>
<span>Average score</span>
<strong>${safeHtml(total ? avgScore : "-")}</strong>
</article>
<article>
<span>Top profile</span>
<strong>${safeHtml(topCandidate?.full_name || "Not selected")}</strong>
</article>
<article>
<span>Ready for outreach</span>
<strong>${safeHtml(readyCount)}</strong>
</article>
`
}

if(!queue.length){
list.innerHTML = `
<div class="ats-bulk-empty-workflow">
<strong>No shortlisted candidates yet</strong>
<span>Go to Candidates and click Shortlist on profiles you want to review.</span>
</div>
`
return
}

list.innerHTML = queue.map((item,index)=>bulkShortlistCandidateCard(item.candidate,item.candidateId,item.meta,index)).join("")
}

function bulkShortlistCandidateCard(candidate,candidateId,meta,index){
let score = candidateRecruiterScore(candidate)
let matched = cleanedCandidateMatchedSkills(candidate).slice(0,5)
let missing = cleanedCandidateMissingSkills(candidate).slice(0,4)
let alreadyMoved = !!bulkWorkflowState.communication[candidateId]
let scoreBand = score >= 75 ? "Strong" : score >= 55 ? "Review" : "Risk"
let scoreClass = score >= 75 ? "is-strong" : score >= 55 ? "is-review" : "is-risk"
let evidence = candidate.ranking_reason || candidate.ai_recruiter_explanation || candidate.recommendation || "Review resume evidence before outreach."

return `
<article class="ats-bulk-shortlist-card">
<div class="ats-bulk-shortlist-rank">
<span>#${index + 1}</span>
<b>${safeHtml(scoreBand)}</b>
</div>

<div class="ats-bulk-shortlist-profile">
<div class="ats-bulk-shortlist-head">
<div>
<h4>${safeHtml(candidate.full_name || "Candidate")}</h4>
<p>${safeHtml(candidate.designation || candidate.domain || "Role signal needs review")}</p>
</div>
<div class="ats-bulk-shortlist-score ${scoreClass}">
<strong>${safeHtml(formatScore(score))}</strong>
<span>AI score</span>
</div>
</div>

<div class="ats-bulk-shortlist-meta">
<span>${safeHtml(candidate.email || "No email")}</span>
<span>${safeHtml(formatExperience(candidate.total_experience_years || candidate.experience || 0))}</span>
<span>${safeHtml(candidate.location || "Location not listed")}</span>
<span>${safeHtml(candidate.last_company_name || candidate.industry || "Company not listed")}</span>
</div>

<div class="ats-bulk-shortlist-evidence">
<section>
<small>Matched skills</small>
<div>${renderBulkSkillPills(matched, "No matched skills")}</div>
</section>
<section>
<small>Gaps to verify</small>
<div>${renderBulkSkillPills(missing, "No major gaps")}</div>
</section>
</div>

<p class="ats-bulk-shortlist-reason">${safeHtml(shortText(evidence, 170))}</p>

<div class="ats-bulk-shortlist-actions">
<span>${safeHtml(alreadyMoved ? "Moved to communication" : meta.status || "Recruiter shortlisted")}</span>
<div>
<button type="button" class="is-secondary" onclick="removeBulkShortlistCandidate('${safeJs(candidateId)}')">Remove</button>
<button type="button" onclick="moveBulkCandidateToCommunication('${safeJs(candidateId)}')" ${alreadyMoved ? "disabled" : ""}>${alreadyMoved ? "In Communication" : "Move to Communication"}</button>
</div>
</div>
</div>
</article>
`
}

function renderBulkSkillPills(items, fallback){
if(!items || !items.length) return `<em>${safeHtml(fallback)}</em>`
return items.map(item=>`<i>${safeHtml(item)}</i>`).join("")
}

function removeBulkShortlistCandidate(candidateId){
let candidate = findBulkCandidate(candidateId)
delete bulkWorkflowState.shortlist[candidateId]
delete bulkWorkflowState.communication[candidateId]
delete bulkWorkflowState.interview[candidateId]
if(candidate) candidate._bulk_status = "Review"
persistActiveBulkSession()
renderBulkWorkflowPages()
renderBulkTable(currentBulkViewResults())
renderTop10Candidates()
}

function bulkEmptyWorkflowText(type){
if(type === "shortlist") return "Shortlist candidates from the bulk results table first."
if(type === "communication") return "Move shortlisted candidates here after recruiter review."
return "Move interested communication candidates here for interview planning."
}

function bulkWorkflowCard(candidate,candidateId,meta,type,index){
let skills = textList(cleanedCandidateMatchedSkills(candidate).slice(0,4), "Skills need review")
let missing = textList(cleanedCandidateMissingSkills(candidate).slice(0,3), "No major gaps listed")
let actionLabel = "Move to Communication"
let actionHandler = `moveBulkCandidateToCommunication('${safeJs(candidateId)}')`
let extraActions = ""

if(type === "communication"){
actionLabel = "Move to Interview"
actionHandler = `moveBulkCandidateToInterview('${safeJs(candidateId)}')`
extraActions = `
<button type="button" class="is-soft" onclick="setBulkCommunicationResponse('${safeJs(candidateId)}','Interested')">Interested</button>
<button type="button" class="is-soft is-danger" onclick="setBulkCommunicationResponse('${safeJs(candidateId)}','Not Interested')">Not Interested</button>
`
}

if(type === "interview"){
actionLabel = "Mark Screened"
actionHandler = `completeBulkInterviewCandidate('${safeJs(candidateId)}')`
}

return `
<article class="ats-bulk-workflow-card">
<div class="ats-bulk-workflow-rank">#${index + 1}</div>
<div class="ats-bulk-workflow-main">
<div class="ats-bulk-workflow-top">
<div>
<h4>${safeHtml(candidate.full_name || "Candidate")}</h4>
<p>${safeHtml(candidate.designation || candidate.domain || "Role signal needs review")}</p>
</div>
<strong>${safeHtml(formatScore(candidate.final_score || 0))}</strong>
</div>
<div class="ats-bulk-workflow-meta">
<span>${safeHtml(candidate.email || "No email")}</span>
<span>${safeHtml(formatExperience(candidate.total_experience_years || candidate.experience || 0))}</span>
<span>${safeHtml(candidate.location || "Location not listed")}</span>
</div>
<p class="ats-bulk-workflow-note"><b>Skills:</b> ${safeHtml(skills)}<br><b>Verify:</b> ${safeHtml(missing)}</p>
<div class="ats-bulk-workflow-footer">
<span>${safeHtml(meta.status || "Ready")}</span>
<div class="ats-bulk-workflow-footer-actions">
${extraActions}
<button type="button" onclick="${actionHandler}">${safeHtml(actionLabel)}</button>
</div>
</div>
</div>
</article>
`
}

function setBulkCommunicationResponse(candidateId,response){
let candidate = findBulkCandidate(candidateId)
if(!candidate || !bulkWorkflowState.communication[candidateId]) return
bulkWorkflowState.communication[candidateId].response = response
bulkWorkflowState.communication[candidateId].status = response
candidate._bulk_status = response === "Interested" ? "Bulk Interested" : "Bulk Not Interested"
persistActiveBulkSession()
renderBulkWorkflowPages()
renderBulkTable(currentBulkViewResults())
renderTop10Candidates()
}

function completeBulkInterviewCandidate(candidateId){
let candidate = findBulkCandidate(candidateId)
if(!candidate || !bulkWorkflowState.interview[candidateId]) return
bulkWorkflowState.interview[candidateId].status = "Screened in bulk workflow"
candidate._bulk_status = "Bulk Screened"
persistActiveBulkSession()
renderBulkWorkflowPages()
renderBulkTable(currentBulkViewResults())
renderTop10Candidates()
}

function updateBulkWorkflowCounts(){
let shortlistCount = Object.keys(bulkWorkflowState.shortlist || {}).length
let communicationCount = Object.keys(bulkWorkflowState.communication || {}).length
let interviewCount = Object.keys(bulkWorkflowState.interview || {}).length

let shortlistCountEl = document.getElementById("bulkShortlistCount")
let communicationCountEl = document.getElementById("bulkCommunicationCount")
let interviewCountEl = document.getElementById("bulkInterviewCount")
let shortlistPill = document.getElementById("bulkShortlistPill")
let communicationPill = document.getElementById("bulkCommunicationPill")
let interviewPill = document.getElementById("bulkInterviewPill")

if(shortlistCountEl) shortlistCountEl.innerText = shortlistCount
if(communicationCountEl) communicationCountEl.innerText = communicationCount
if(interviewCountEl) interviewCountEl.innerText = interviewCount
if(shortlistPill) shortlistPill.innerText = `${shortlistCount} candidate${shortlistCount === 1 ? "" : "s"}`
if(communicationPill) communicationPill.innerText = `${communicationCount} candidate${communicationCount === 1 ? "" : "s"}`
if(interviewPill) interviewPill.innerText = `${interviewCount} candidate${interviewCount === 1 ? "" : "s"}`
}

// ---------------- DOWNLOAD CSV ----------------

function downloadCSV(){

let jobId=document.getElementById("jobIdResults").value

if(!jobId){
alert("Enter Job ID")
return
}

window.open(API+"/download-csv/"+jobId)

}
// ---------------- SHOW ALL JOBS ----------------

function showAllJobs(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

let container=document.getElementById("jobCards")

if(!container) return

container.innerHTML=""

jobs.forEach(job=>{

container.innerHTML+=`

<div class="job-card">

<div>

<div class="job-title">
${job.job_title}
</div>

<div class="company-name">
${job.company_name}
</div>

<div class="job-info">

<div><span>Location:</span> ${job.location || "N/A"}</div>

<div><span>Salary:</span> ${job.salary_range || "Not specified"}</div>

<div><span>Job Type:</span> ${job.job_type || "N/A"}</div>

</div>

<div class="job-desc">

<strong>Job Description:</strong><br>

${job.jd_text ? job.jd_text.substring(0,120) + "..." : "No description"}

</div>

</div>

<button
class="result-btn"
onclick="openJobResult('${job.id || job.job_id}','${job.job_title}')">

View Results

</button>

<div class="job-footer">

<span>Applicants: ${job.total_applicants || 0}</span>
<span>Top Score: ${job.top_score || 0}</span>

</div>

</div>

`

})

})

}
// ---------------- TOGGLE DROPDOWN ----------------
function toggleSkillDropdown(){
    let dropdown = document.getElementById("skillDropdown")
    dropdown.classList.toggle("hidden")
}

// ---------------- AUTO CLOSE ----------------
document.addEventListener("click", function(e){
    let dropdown = document.getElementById("skillDropdown")
    let box = document.querySelector(".skill-box")

    if(!box.contains(e.target) && !dropdown.contains(e.target)){
        dropdown.classList.add("hidden")
    }
})

// ---------------- GET SELECTED SKILLS ----------------
function getSelectedSkills(){
    let checkboxes = document.querySelectorAll("#skillDropdown input:checked")
    return [...checkboxes].map(c => c.value.toLowerCase())
}

// ---------------- LOAD SKILLS FROM JD ----------------
function loadSkillsFromJD(jdText){

    let skills = normalizeScreeningSkills([], jdText)

    let container = document.getElementById("skillDropdown")
    container.innerHTML = ""

    skills.forEach(skill => {
        container.innerHTML += `
        <label>
            <input type="checkbox" value="${safeHtml(skill)}">
            <span>${safeHtml(skill)}</span>
        </label>
        `
    })
}

// ---------------- APPLY FILTER ----------------
function applyResultFilters(){

    let location = document.getElementById("resultLocationFilter").value.toLowerCase()
    let score = document.getElementById("resultScoreFilter").value

    let selectedSkills = getSelectedSkills()

    let table = document.getElementById("resultsTable")
    let rows = table.getElementsByTagName("tr")

    for(let i = 0; i < rows.length; i++){

        let row = rows[i]
        let text = row.dataset.searchText || row.innerText.toLowerCase()

        let show = true

        // LOCATION
        if(location && !text.includes(location)){
            show = false
        }

        // SKILLS
        if(selectedSkills.length > 0){
            let match = selectedSkills.every(skill => text.includes(skill))
            if(!match){
                show = false
            }
        }

        // SCORE
        if(score){
            let rowScore = Number(row.dataset.score || 0)
            if(rowScore < Number(score)){
                show = false
            }
        }

        row.style.display = show ? "" : "none"
    }
}


function renderSkillDropdown(){

    let container = document.getElementById("skillDropdown")
    if(!container) return

    container.innerHTML = ""

    if(!currentSkills || currentSkills.length === 0){
        container.innerHTML = "<p style='font-size:12px'>No skills</p>"
        return
    }

    currentSkills.forEach(skill => {
        container.innerHTML += `
        <label>
            <input type="checkbox" value="${safeHtml(skill)}">
            <span>${safeHtml(skill)}</span>
        </label>
        `
    })
}



// OPEN TOP 10 PAGE


function openTopCandidates(){

showPage("topCandidate")

let table=document.getElementById("topCandidateTable")

if(!table) return

table.innerHTML=""

let sorted=[...currentResults]
.sort(compareCandidateRank)
.slice(0,10)

let total = sorted.length
let bestScore = sorted.reduce((max,c)=>Math.max(max, candidateRecruiterScore(c)), 0)
let avgScore = total
? sorted.reduce((sum,c)=>sum + (Number(c.final_score) || 0), 0) / total
: 0
let shortlisted = sorted.filter(c=>safeText(getDisplayStatus(c)).toLowerCase().includes("shortlist")).length

let totalEl = document.getElementById("top10TotalCount")
let bestEl = document.getElementById("top10BestScore")
let avgEl = document.getElementById("top10AvgScore")
let shortlistedEl = document.getElementById("top10ShortlistedCount")
let metaEl = document.getElementById("top10BoardMeta")

if(totalEl) totalEl.innerText = total
if(bestEl) bestEl.innerText = formatScore(bestScore)
if(avgEl) avgEl.innerText = formatScore(avgScore)
if(shortlistedEl) shortlistedEl.innerText = shortlisted
if(metaEl) metaEl.innerText = `${total} candidates`

if(sorted.length === 0){
table.innerHTML = `
<tr class="ats-top10-empty-row">
<td colspan="6">
<div class="ats-top10-empty">
<span>AI</span>
<strong>No ranked candidates yet</strong>
<p>Candidate results will appear here after resumes are screened for this job.</p>
</div>
</td>
</tr>
`
return
}

sorted.forEach((c,i)=>{
let candidateId = c.resume_id || c.id || ""
let profileId = registerCandidateProfile(c)
let status = getDisplayStatus(c)
let score = Number(c.final_score) || 0
let band = scoreBand(score, c)
let initials = candidateInitials(c.full_name)
let matchedSkills = normalizeScreeningSkills(c.matched_skills).slice(0,3)
let location = safeText(c.location || "").trim() || "Location not listed"
let experience = formatExperience(c.total_experience_years)
let company = safeText(c.last_company_name || "").trim() || "Company not listed"
let rankClass = i === 0 ? "is-first" : i === 1 ? "is-second" : i === 2 ? "is-third" : ""
let skillPills = matchedSkills.length
? matchedSkills.map(skill=>`<span>${safeHtml(skill)}</span>`).join("")
: `<span>No matched skills listed</span>`

table.innerHTML+=`

<tr class="ats-top10-row ${rankClass}">

<td>
<span class="ats-top10-rank">#${i+1}</span>
</td>

<td>
<div class="ats-top10-candidate">
<button type="button" class="ats-top10-avatar ats-top10-profile-trigger" data-profile-candidate-id="${safeHtml(profileId)}" title="Open candidate profile">${safeHtml(initials)}</button>
<div>
<button type="button" class="ats-top10-name-btn" data-profile-candidate-id="${safeHtml(profileId)}">${safeHtml(c.full_name || "Unnamed Candidate")}</button>
<small>${safeHtml(c.email || "Email not available")}</small>
</div>
</div>
</td>

<td>
<div class="ats-top10-signals">
<div><span>Experience</span><strong>${safeHtml(experience)}</strong></div>
<div><span>Location</span><strong>${safeHtml(location)}</strong></div>
<div><span>Last Company</span><strong>${safeHtml(company)}</strong></div>
<div class="ats-top10-skills">${skillPills}</div>
</div>
</td>

<td>
<div class="ats-top10-score ${band.className}">
<strong>${safeHtml(formatScore(score))}</strong>
<span>${safeHtml(band.label)}</span>
<div><i style="width:${Math.min(Math.max(score,0),100)}%"></i></div>
</div>
</td>

<td>
<span class="ats-result-status ${getStatusClass(status)}">${safeHtml(status)}</span>
</td>

<td>
<div class="ats-top10-actions">
<button onclick="openAIExplanation('${safeJs(candidateId)}')" class="ats-top10-action is-ai">AI Explain</button>
<button onclick="shortlistCandidate('${safeJs(candidateId)}', '${safeJs(status)}')" class="ats-top10-action is-shortlist">Shortlist</button>
<button onclick="rejectCandidate('${safeJs(candidateId)}')" class="ats-top10-action is-reject">Reject</button>
</div>
</td>

</tr>

`

})

table.querySelectorAll("[data-profile-candidate-id]").forEach(trigger => {
trigger.onclick = event => {
event.preventDefault()
event.stopPropagation()
candidateProfileReturnContext = getCandidateProfileReturnContext(trigger)
openRankedCandidateProfile(trigger.dataset.profileCandidateId || "")
}
})

}

function normalizeCandidateForProfile(candidate={}){
let name = candidate.full_name || candidate.name || candidate.candidate_name || "Unnamed Candidate"
let score = candidate.final_score ?? candidate.score ?? candidate.ai_score ?? 0
let experience = candidate.total_experience_years ?? candidate.experience_years ?? candidate.experience ?? 0
let lastCompany = candidate.last_company_name || candidate.last_company || candidate.company_name || ""

return {
...candidate,
id: candidate.id || candidate.resume_id || candidate.candidate_id || candidate.email || name,
resume_id: candidate.resume_id || candidate.id || candidate.candidate_id || "",
candidate_id: candidate.candidate_id || candidate.id || candidate.resume_id || "",
full_name: name,
name,
email: candidate.email || "",
phone: candidate.phone || "",
location: candidate.location || "",
designation: candidate.designation || candidate.job_title || candidate.role || window.currentJobTitle || "",
total_experience_years: experience,
experience,
last_company_name: lastCompany,
education: candidate.education || "",
final_score: score,
score,
status: candidate.status || candidate.communication_status || candidate.interview_status || "",
matched_skills: candidate.matched_skills || candidate.skills_matched || "",
missing_skills: candidate.missing_skills || candidate.skill_gaps || "",
key_skills: candidate.key_skills || candidate.skills || candidate.matched_skills || "",
skill_match_percent: candidate.skill_match_percent || candidate.match_percent || "",
rank_score: candidate.rank_score ?? score,
fit_band: candidate.fit_band || "",
confidence_score: candidate.confidence_score ?? "",
resume_quality_score: candidate.resume_quality_score ?? "",
ranking_reason: candidate.ranking_reason || "",
client_summary: candidate.client_summary || "",
recruiter_trust: candidate.recruiter_trust || {},
risk_points: candidate.risk_points || [],
evidence_points: candidate.evidence_points || [],
latest_note: candidate.latest_note || "",
note_count: candidate.note_count || 0,
tags: candidate.tags || [],
projects: candidate.projects || [],
resume_available: candidate.resume_available,
resume_original_filename: candidate.resume_original_filename || "",
resume_content_type: candidate.resume_content_type || ""
}
}

function candidateIdentity(candidate){
return safeText(candidate?.resume_id || candidate?.id || candidate?.candidate_id || candidate?.email || candidate?.full_name || candidate?.name || "")
}

function registerCandidateProfile(candidate){
let normalized = normalizeCandidateForProfile(candidate || {})
let key = candidateIdentity(normalized)
if(key){
candidateProfileStore[key] = {
...(candidateProfileStore[key] || {}),
...normalized
}
}
return key
}

function candidateProfileNameButton(candidate, className="ats-candidate-name-link"){
let normalized = normalizeCandidateForProfile(candidate || {})
let key = registerCandidateProfile(normalized)
return `<button type="button" class="${safeHtml(className)}" data-profile-candidate-id="${safeHtml(key)}">${safeHtml(normalized.full_name || "Unnamed Candidate")}</button>`
}

function findCurrentCandidate(candidateId){
let target = safeText(candidateId)
if(candidateProfileStore[target]) return candidateProfileStore[target]
let candidate = (currentResults || []).find(item => candidateIdentity(item) === target)
if(!candidate) return null
let key = registerCandidateProfile(candidate)
return candidateProfileStore[key] || normalizeCandidateForProfile(candidate)
}

function candidateProfileNeedsReparse(candidate){
let combined = [
candidate?.phone,
candidate?.education,
candidate?.projects,
candidate?.ranking_reason,
candidate?.fit_band,
candidate?.ai_recommendation
].map(value => typeof value === "string" ? value : JSON.stringify(value || "")).join(" ")
return Boolean(
(/\b(19|20)\d{2}\s*(?:-|\u2013|\u2014|to)\s*(19|20)\d{2}\b/.test(safeText(candidate?.phone))) ||
(/\b(profile needs review|parser quality|resume section noise|project_noise_detected|company_needs_review|education_needs_review|phone_needs_review|suspicious_last_company)\b/i.test(combined)) ||
(/\b(worked on a collaborative team|nashville software school wiles|jupyter|juypter|nashvillebuildingpermits)\b/i.test(combined)) ||
((Number(candidate?.total_experience_years) || 0) <= 0 && /\b(vitality|wiles|sesac|haber|experience)\b/i.test(combined))
)
}

function candidateProjectsToText(projects){
if(!Array.isArray(projects)) return safeText(projects || "")
return projects.map(item => {
if(typeof item === "string") return safeText(item)
let name = safeText(item?.name || item?.title || "").trim()
let desc = safeText(item?.description || item?.summary || "").trim()
let tools = Array.isArray(item?.technologies) ? item.technologies.join(", ") : safeText(item?.technologies || item?.tools || "")
return [name, desc, tools].filter(Boolean).join(" - ")
}).filter(Boolean).join("\n")
}

function candidateQaActions(candidate, candidateId, showReparse){
let canReparse = candidate?.resume_available !== false
let canDownload = candidate?.resume_available !== false && Boolean(candidateId)
let downloadTitle = canDownload
? (candidate?.resume_original_filename || "Download resume")
: "Resume file is not available"
return `
<div class="ats-candidate-qa-actions">
<button onclick="openResumeDownload('${safeJs(candidateId)}')" class="ats-candidate-action is-secondary" title="${safeHtml(downloadTitle)}" ${canDownload ? "" : "disabled"}>Download Resume</button>
<button id="candidateReparseBtn" onclick="reparseCandidateProfile('${safeJs(candidateId)}')" class="ats-candidate-action is-secondary" ${canReparse ? "" : "disabled"}>${showReparse ? "Re-parse Resume" : "Re-parse if Needed"}</button>
<button onclick="openCandidateEditModal('${safeJs(candidateId)}')" class="ats-candidate-action is-secondary">Edit Data</button>
<button id="candidateRereviewBtn" onclick="rereviewCandidateProfile('${safeJs(candidateId)}')" class="ats-candidate-action is-secondary">Re-review</button>
</div>
`
}

function updateCandidateProfileCache(candidate){
let normalized = normalizeCandidateForProfile(candidate || {})
let key = registerCandidateProfile(normalized)
currentResults = (currentResults || []).map(item => {
let identity = candidateIdentity(item)
if(identity && (identity === key || identity === normalized.resume_id || identity === normalized.id)){
return {...item, ...normalized}
}
return item
})
return candidateProfileStore[key] || normalized
}

function setCandidateProfileHeader(title, subtitle, backLabel, backAction){
let titleEl = document.getElementById("candidateProfileTitle")
let page = document.getElementById("candidateProfilePage")
let copyEl = page ? page.querySelector(".ats-candidate-profile-header p") : null
let backBtn = page ? page.querySelector(".ats-candidate-profile-header .ats-back-btn") : null

if(titleEl) titleEl.innerText = title
if(copyEl) copyEl.innerText = subtitle
if(backBtn){
backBtn.innerText = backLabel
backBtn.setAttribute("onclick", backAction)
}
}

function renderStoredCandidateProfile(candidate, options={}){
let content = document.getElementById("candidateProfileContent")
if(!content || !candidate) return

let jobId = options.jobId || window.currentJobId || candidate.job_id || ""
let jobTitle = options.jobTitle || window.currentJobTitle || "Selected Job"
let score = candidateRecruiterScore(candidate)
let band = scoreBand(score, candidate)
let skills = normalizeList(candidate.key_skills)
let displayName = candidateSafeDisplay(candidate, "name", "Needs manual review")
let displayEmail = candidateSafeDisplay(candidate, "email", "Needs manual review")
let displayLocation = candidateSafeDisplay(candidate, "location", "Needs manual review")
let education = safeText(candidateSafeDisplay(candidate, "education", "Needs manual review"))
let experience = candidateSafeDisplay(candidate, "experience", "Needs manual review")
let status = getDisplayStatus(candidate) || getStatus(score)
let alreadyShortlisted = safeText(status).toLowerCase().includes("shortlist")
let candidateId = candidate.resume_id || candidate.id || ""
let showReparse = candidate.resume_available !== false && candidateProfileNeedsReparse(candidate)
let profileNote = options.profileNote || "Candidate profile built from stored resume, score, JD match, and recruiter workflow signals."
let trust = candidate.recruiter_trust || {}
let evidencePoints = normalizeList(trust.evidence_points || candidate.evidence_points)
let riskPoints = normalizeList(trust.risk_points || candidate.risk_points)
let profileTags = Array.isArray(candidate.tags) ? candidate.tags : []
let tagMarkup = profileTags.length
? profileTags.map(tag => `<span class="ats-fit-pill">${safeHtml(tag.tag || tag)}</span>`).join("")
: `<span class="ats-muted">No tags yet</span>`
let evidenceMarkup = evidencePoints.length
? evidencePoints.map(item => `<li>${safeHtml(item)}</li>`).join("")
: `<li>Open resume evidence before client submission.</li>`
let riskMarkup = riskPoints.length
? riskPoints.map(item => `<li>${safeHtml(item)}</li>`).join("")
: `<li>No major risk flags stored.</li>`

content.innerHTML = `
<section class="ats-candidate-profile-grid">
<div class="ats-candidate-left-column">
<div class="ats-candidate-hero-panel">
<div class="ats-candidate-hero-top">
<div class="ats-candidate-avatar-large">${safeHtml(candidateInitials(candidate.full_name))}</div>
<div class="ats-candidate-main-copy">
<span class="ats-fit-pill ${band.className}">${safeHtml(band.label)}</span>
<h3>${safeHtml(displayName)}</h3>
<p>${safeHtml(candidate.designation || jobTitle)}</p>
</div>
</div>

${candidateQaActions(candidate, candidateId, showReparse)}

<div class="ats-candidate-score-wrap">
<div class="ats-score-ring" style="--score:${Math.min(Math.max(score,0),100)}">
<strong>${safeHtml(formatScore(score))}</strong>
<span>AI score</span>
</div>
<div>
<h4 id="topCandidateProfileStatus">${safeHtml(alreadyShortlisted ? "Shortlisted" : status)}</h4>
<p>${safeHtml(profileNote)}</p>
</div>
</div>

<div class="ats-candidate-primary-actions">
<button onclick="shortlistTopCandidate('${safeJs(candidateId)}','${safeJs(jobId)}')" class="ats-candidate-action is-shortlist ${alreadyShortlisted ? "is-done" : ""}" ${alreadyShortlisted ? "disabled" : ""}>${alreadyShortlisted ? "Shortlisted" : "Shortlist Candidate"}</button>
<a href="mailto:${safeHtml(candidate.email || "")}" class="ats-candidate-action ${candidate.email ? "" : "is-disabled"}">Email Candidate</a>
<a href="tel:${safeHtml(candidate.phone || "")}" class="ats-candidate-action is-secondary ${candidate.phone ? "" : "is-disabled"}">Call</a>
<button onclick="assignCandidateToMe('${safeJs(candidateId)}')" class="ats-candidate-action is-secondary">Assign to Me</button>
</div>
</div>

${topCandidateSkillCoverage(candidate)}

<div class="ats-candidate-panel">
<div class="ats-panel-title-row">
<div>
<h4>Recruiter Decision Evidence</h4>
<p>Why this candidate should move forward or stay in review.</p>
</div>
<span>${safeHtml(trust.recruiter_recommendation || "review")}</span>
</div>
<ul class="ats-shortlist-insight-list">${evidenceMarkup}</ul>
<h4>Risk Checks</h4>
<ul class="ats-shortlist-insight-list">${riskMarkup}</ul>
</div>
</div>

<div class="ats-candidate-right-column">
<div class="ats-candidate-summary-panel">
<h4>Candidate Snapshot</h4>
<div class="ats-candidate-detail-grid">
${topCandidateDetail("Email", displayEmail)}
${topCandidateDetail("Phone", candidateSafeDisplay(candidate, "phone", "Needs manual review"))}
${topCandidateDetail("Location", displayLocation)}
${topCandidateDetail("Experience", experience)}
${topCandidateDetail("Last Company", candidateSafeDisplay(candidate, "last_company", "Needs manual review"))}
${topCandidateDetail("Education", education)}
</div>
</div>

<div class="ats-candidate-panel ats-candidate-skills-panel">
<div class="ats-panel-title-row">
<div>
<h4>Skills Match</h4>
<p>Extracted from the candidate resume.</p>
</div>
<span>${skills.length} skills</span>
</div>
<div class="ats-skill-cloud">
${topCandidateSkillPills(skills)}
</div>
</div>

<div class="ats-candidate-panel ats-candidate-projects-panel">
<div class="ats-panel-title-row">
<div>
<h4>Project Evidence</h4>
<p>Resume projects and work examples used for screening context.</p>
</div>
<span>Resume proof</span>
</div>
<div id="topCandidateProjects">
${topCandidateProjectEvidence(candidate.projects)}
</div>
</div>

<div class="ats-candidate-panel">
<div class="ats-panel-title-row">
<div>
<h4>Recruiter Notes & Tags</h4>
<p>Internal agency notes stay out of client report.</p>
</div>
<span id="candidateNoteCount">${safeHtml(candidate.note_count || 0)} notes</span>
</div>
<div id="candidateTagList" class="ats-skill-cloud">${tagMarkup}</div>
<div class="ats-candidate-detail-grid">
<input id="candidateQuickTag" placeholder="Add tag e.g. client-ready" class="border p-3 rounded w-full">
<button onclick="addCandidateTag('${safeJs(candidateId)}')" class="ats-candidate-action is-secondary">Add Tag</button>
</div>
<textarea id="candidateRecruiterNote" placeholder="Add recruiter note for screening, client feedback, or follow-up." class="border p-3 rounded w-full" style="min-height:90px;margin-top:12px"></textarea>
<button onclick="addCandidateNote('${safeJs(candidateId)}')" class="ats-candidate-action is-shortlist" style="margin-top:10px">Save Note</button>
<div id="candidateNotesList" style="margin-top:12px">${candidate.latest_note ? `<p>${safeHtml(candidate.latest_note)}</p>` : `<p class="ats-muted">No notes yet.</p>`}</div>
</div>
</div>
</section>
`
loadCandidateWorkspace(candidateId)
}

async function loadCandidateWorkspace(candidateId){
if(!candidateId) return
try{
let res = await fetch(API + "/candidate-workspace/" + encodeURIComponent(candidateId))
if(!res.ok) return
let data = await res.json()
let notesBox = document.getElementById("candidateNotesList")
let noteCount = document.getElementById("candidateNoteCount")
let tagBox = document.getElementById("candidateTagList")
let notes = Array.isArray(data.notes) ? data.notes : []
let tags = Array.isArray(data.tags) ? data.tags : []
if(noteCount) noteCount.innerText = `${notes.length} notes`
if(notesBox){
notesBox.innerHTML = notes.length
? notes.map(note => `<p>${safeHtml(note.body)}<br><small>${safeHtml(note.created_at || "")}</small></p>`).join("")
: `<p class="ats-muted">No notes yet.</p>`
}
if(tagBox){
tagBox.innerHTML = tags.length
? tags.map(tag => `<span class="ats-fit-pill">${safeHtml(tag.tag)}</span>`).join("")
: `<span class="ats-muted">No tags yet</span>`
}
}catch(err){
}
}

async function addCandidateNote(candidateId){
let input = document.getElementById("candidateRecruiterNote")
let body = safeText(input?.value).trim()
if(!candidateId || !body){
alert("Add a note first.")
return
}
let res = await fetch(API + "/candidate-note/" + encodeURIComponent(candidateId), {
method:"POST",
headers:authHeaders(),
body:JSON.stringify({body})
})
if(!res.ok){
alert("Could not save note.")
return
}
if(input) input.value = ""
await loadCandidateWorkspace(candidateId)
}

async function addCandidateTag(candidateId){
let input = document.getElementById("candidateQuickTag")
let tag = safeText(input?.value).trim()
if(!candidateId || !tag){
alert("Add a tag first.")
return
}
let res = await fetch(API + "/candidate-tag/" + encodeURIComponent(candidateId), {
method:"POST",
headers:authHeaders(),
body:JSON.stringify({tag})
})
if(!res.ok){
alert("Could not save tag.")
return
}
if(input) input.value = ""
await loadCandidateWorkspace(candidateId)
}

async function assignCandidateToMe(candidateId){
if(!candidateId) return
let res = await fetch(API + "/candidate-assign-me/" + encodeURIComponent(candidateId), {
method:"POST",
headers:authHeaders()
})
if(!res.ok){
alert("Could not assign candidate.")
return
}
alert("Candidate assigned to you.")
}

async function reparseCandidateProfile(candidateId){
if(!candidateId) return
let btn = document.getElementById("candidateReparseBtn")
let oldText = btn ? btn.innerText : ""
if(btn){
btn.disabled = true
btn.innerText = "Re-parsing..."
}
try{
let res = await fetch(API + "/candidate-reparse/" + encodeURIComponent(candidateId), {
method:"POST",
headers:authHeaders()
})
let data = await res.json().catch(()=>({}))
if(!res.ok){
alert(data.detail || "Could not re-parse this candidate.")
return
}
let updated = updateCandidateProfileCache(data.candidate || {})
renderStoredCandidateProfile(updated, {
jobId: window.currentJobId || updated.job_id || "",
jobTitle: window.currentJobTitle || updated.designation || "Selected Job",
profileNote: "Candidate profile was re-parsed from the stored resume and refreshed."
})
alert("Candidate profile re-parsed and updated.")
}catch(err){
alert("Could not re-parse this candidate.")
}finally{
if(btn){
btn.disabled = false
btn.innerText = oldText || "Re-parse Resume"
}
}
}

function closeCandidateEditModal(){
let modal = document.getElementById("candidateEditModal")
if(modal) modal.remove()
}

function candidateEditField(id, label, value, type="text"){
return `
<label class="ats-manual-field">
<span>${safeHtml(label)}</span>
<input id="${safeHtml(id)}" type="${safeHtml(type)}" value="${safeHtml(value || "")}">
</label>
`
}

function candidateEditTextarea(id, label, value, rows=4){
return `
<label class="ats-manual-field ats-manual-field-wide">
<span>${safeHtml(label)}</span>
<textarea id="${safeHtml(id)}" rows="${rows}">${safeHtml(value || "")}</textarea>
</label>
`
}

function openCandidateEditModal(candidateId){
let candidate = findCurrentCandidate(candidateId)
if(!candidate){
alert("Candidate data is not loaded yet. Open the profile again and try edit.")
return
}
closeCandidateEditModal()
let modal = document.createElement("div")
modal.id = "candidateEditModal"
modal.className = "ats-manual-modal"
modal.innerHTML = `
<div class="ats-manual-modal-card">
<div class="ats-manual-modal-head">
<div>
<h3>Edit Candidate Data</h3>
<p>Correct parser mistakes, then save and re-review this candidate.</p>
</div>
<button type="button" onclick="closeCandidateEditModal()" class="ats-manual-close">x</button>
</div>
<div class="ats-manual-grid">
${candidateEditField("manualFullName", "Full name", candidate.full_name)}
${candidateEditField("manualDesignation", "Role / designation", candidate.designation)}
${candidateEditField("manualEmail", "Email", candidate.email, "email")}
${candidateEditField("manualPhone", "Phone", candidate.phone)}
${candidateEditField("manualLocation", "Location", candidate.location)}
${candidateEditField("manualExperience", "Experience years", candidate.total_experience_years, "number")}
${candidateEditField("manualCompany", "Last company", candidate.last_company_name)}
${candidateEditTextarea("manualEducation", "Education", candidate.education, 3)}
${candidateEditTextarea("manualSkills", "Key skills", normalizeList(candidate.key_skills).join(", "), 4)}
${candidateEditTextarea("manualMatched", "Matched skills", normalizeList(candidate.matched_skills).join(", "), 3)}
${candidateEditTextarea("manualMissing", "Missing skills", normalizeList(candidate.missing_skills).join(", "), 3)}
${candidateEditTextarea("manualProjects", "Project evidence", candidateProjectsToText(candidate.projects), 5)}
</div>
<div class="ats-manual-actions">
<button type="button" onclick="closeCandidateEditModal()" class="ats-candidate-action is-secondary">Cancel</button>
<button id="candidateManualSaveBtn" type="button" onclick="saveCandidateManualEdit('${safeJs(candidateId)}')" class="ats-candidate-action is-shortlist">Save & Re-review</button>
</div>
</div>
`
document.body.appendChild(modal)
}

async function saveCandidateManualEdit(candidateId){
if(!candidateId) return
let btn = document.getElementById("candidateManualSaveBtn")
let oldText = btn ? btn.innerText : ""
if(btn){
btn.disabled = true
btn.innerText = "Saving..."
}
let payload = {
full_name: document.getElementById("manualFullName")?.value || "",
designation: document.getElementById("manualDesignation")?.value || "",
email: document.getElementById("manualEmail")?.value || "",
phone: document.getElementById("manualPhone")?.value || "",
location: document.getElementById("manualLocation")?.value || "",
total_experience_years: document.getElementById("manualExperience")?.value || 0,
last_company_name: document.getElementById("manualCompany")?.value || "",
education: document.getElementById("manualEducation")?.value || "",
key_skills: document.getElementById("manualSkills")?.value || "",
matched_skills: document.getElementById("manualMatched")?.value || "",
missing_skills: document.getElementById("manualMissing")?.value || "",
projects: document.getElementById("manualProjects")?.value || "",
review: true
}
try{
let res = await fetch(API + "/candidate-update/" + encodeURIComponent(candidateId), {
method:"POST",
headers:authHeaders(),
body:JSON.stringify(payload)
})
let data = await res.json().catch(()=>({}))
if(!res.ok){
alert(data.detail || "Could not update candidate data.")
return
}
let updated = updateCandidateProfileCache(data.candidate || {})
closeCandidateEditModal()
renderStoredCandidateProfile(updated, {
jobId: window.currentJobId || updated.job_id || "",
jobTitle: window.currentJobTitle || updated.designation || "Selected Job",
profileNote: "Candidate data was manually edited and re-reviewed from the corrected fields."
})
alert("Candidate data updated and re-reviewed.")
}catch(err){
alert("Could not update candidate data.")
}finally{
if(btn){
btn.disabled = false
btn.innerText = oldText || "Save & Re-review"
}
}
}

async function rereviewCandidateProfile(candidateId){
if(!candidateId) return
let btn = document.getElementById("candidateRereviewBtn")
let oldText = btn ? btn.innerText : ""
if(btn){
btn.disabled = true
btn.innerText = "Reviewing..."
}
try{
let res = await fetch(API + "/candidate-rereview/" + encodeURIComponent(candidateId), {
method:"POST",
headers:authHeaders()
})
let data = await res.json().catch(()=>({}))
if(!res.ok){
alert(data.detail || "Could not re-review candidate.")
return
}
let updated = updateCandidateProfileCache(data.candidate || {})
renderStoredCandidateProfile(updated, {
jobId: window.currentJobId || updated.job_id || "",
jobTitle: window.currentJobTitle || updated.designation || "Selected Job",
profileNote: "Candidate profile was re-reviewed from the current stored data."
})
alert("Candidate re-reviewed.")
}catch(err){
alert("Could not re-review candidate.")
}finally{
if(btn){
btn.disabled = false
btn.innerText = oldText || "Re-review"
}
}
}

var openRankedCandidateProfile = function(candidateId){
let candidate = findCurrentCandidate(candidateId)

if(!candidate){
alert("Candidate profile data not found. Please reload the candidate table.")
return
}

let returnContext = candidateProfileReturnContext || {
label: "Back to Candidates",
action: "showPage('results')"
}

showPage("candidateProfile")
setCandidateProfileHeader(
`${candidate.full_name || "Candidate"} - Profile`,
"Stored candidate profile with resume signals, JD skill coverage, contact details, and project evidence. No AI summary is generated here.",
returnContext.label,
returnContext.action
)
renderStoredCandidateProfile(candidate, {
jobId: window.currentJobId || candidate.job_id || "",
jobTitle: window.currentJobTitle || candidate.designation || "Selected Job",
profileNote: "Stored profile view from ranking data. No AI summary or expensive model call is used on this page."
})
}


async function rejectCandidate(id){

    if(!confirm("Reject this candidate?")) return

    let res = await fetch(API + "/reject/" + id, {
        method: "POST"
    })

    let data = await res.json()

    if(data.error){
        alert("Error: " + data.error)
        return
    }

    alert("OK Candidate Rejected")

    // * IMPORTANT: refresh BOTH views

    if(currentJobId){
        await loadResults(currentJobId)
    }

    openTopCandidates()   // star refresh top 10 table
}

async function shortlistCandidate(id, currentStatus){

    // Warning: Rejected case
    if(currentStatus === "Rejected"){

        let confirmAction = confirm(
            "Warning: This candidate is already rejected.\nAre you sure you want to shortlist?"
        )

        if(!confirmAction){
            return
        }

    } else {

        let confirmAction = confirm("Shortlist this candidate?")
        if(!confirmAction){
            return
        }

    }

    let res = await fetch(API + "/shortlist/" + id,{
        method:"POST"
    })

    let data = await res.json()

    if(data.error){
        alert("Error: " + data.error)
        return
    }

    alert("OK " + data.message)

    // * refresh UI
    loadResults(currentJobId)
    openTopCandidates()
}


function openAIExplanation(id){

    window.location.href =
    "ai_explanation.html?resume_id=" + encodeURIComponent(id)

}

function showExplanation(i){

let c = currentResults[i]

// agar backend se ho to force frontend
let base = window.location.origin.includes("8000")
? "http://127.0.0.1:5500"
: window.location.origin

window.open(
base + "/ai_explanation.html?resume_id=" + c.resume_id,
"_blank"
)

}

// CLOSE MODAL

function closeExplain(){

document.getElementById("explainModal").classList.add("hidden")

}
function openAllCandidates(){

document.getElementById("topCandidatePage").classList.add("hidden")
document.getElementById("jobResultPage").classList.remove("hidden")

}


function openInsights(){

showPage("insight")

generateInsights()

}

function compactEducationLabel(value){
let text = safeText(value).replace(/\s+/g," ").trim()
if(!text) return "Unknown"
return text.length > 74 ? text.slice(0, 71).trim() + "..." : text
}

function renderEducationSignals(education, totalCandidates){
let box = document.getElementById("insightEducationList")
if(!box) return

let rows = Object.entries(education || {})
.filter(([, count]) => Number(count) > 0)
.sort((a,b)=>b[1]-a[1])

if(!rows.length){
box.innerHTML = `<div class="ats-education-empty">No education data available.</div>`
return
}

let visible = rows.slice(0, 5)
let remaining = rows.slice(5).reduce((sum, [, count]) => sum + Number(count || 0), 0)
if(remaining){
visible.push(["Other education backgrounds", remaining])
}

box.innerHTML = visible.map(([label, count], index)=>{
let percent = totalCandidates ? Math.round((Number(count || 0) / totalCandidates) * 100) : 0
return `
<article class="ats-education-row">
<div class="ats-education-row-main">
<span>${safeHtml(compactEducationLabel(label))}</span>
<strong>${safeHtml(count)} ${Number(count) === 1 ? "candidate" : "candidates"}</strong>
</div>
<div class="ats-education-meter" style="--edu-percent:${percent}%;--edu-index:${index};">
<span></span>
</div>
<small>${percent}% of pool</small>
</article>
`
}).join("")
}

function candidateSkillEvidence(candidate){
let signals = buildCandidateSkillSignals(candidate || {})
return uniqueCleanList([
...signals.candidateCoverage,
...signals.matched,
...normalizeList(candidate?.matched_skills).flatMap(expandSkillSignal),
...normalizeList(candidate?.key_skills).flatMap(expandSkillSignal)
])
}

function buildJdSkillCoverage(results){
let jdSkills = uniqueCleanList((currentSkills || []).flatMap(expandSkillSignal))

if(!jdSkills.length){
let jdSignalSources = []
;(results || []).forEach(candidate=>{
jdSignalSources.push(candidate?.matched_skills || "")
jdSignalSources.push(candidate?.missing_skills || "")
})
jdSkills = uniqueCleanList(jdSignalSources.flatMap(expandSkillSignal))
}

return jdSkills.map(skill=>{
let count = (results || []).filter(candidate => candidateCoversSkill(skill, candidateSkillEvidence(candidate))).length
return [skill, count]
})
}

function generateInsights(){

if(!currentResults || currentResults.length==0){
alert("No candidate data available")
return
}

Object.values(insightCharts).forEach(chart => chart.destroy())
insightCharts = {}

let education={}
let scoreBuckets=[0,0,0,0,0]
let expBuckets={"0-1":0,"1-3":0,"3-5":0,"5+":0}
let totalScore=0
let totalExp=0
let topTalent=0

currentResults.forEach(c=>{

/* EDUCATION */

let edu=c.education || "Unknown"
education[edu]=(education[edu]||0)+1

/* SCORE */

let score=c.final_score || 0
totalScore += score
if(score >= 80) topTalent++

if(score<20) scoreBuckets[0]++
else if(score<40) scoreBuckets[1]++
else if(score<60) scoreBuckets[2]++
else if(score<80) scoreBuckets[3]++
else scoreBuckets[4]++

/* EXPERIENCE */

let exp=c.total_experience_years || 0
totalExp += exp

if(exp<=1) expBuckets["0-1"]++
else if(exp<=3) expBuckets["1-3"]++
else if(exp<=5) expBuckets["3-5"]++
else expBuckets["5+"]++

})

let totalCandidates = currentResults.length
let avgScore = totalCandidates ? Math.round(totalScore / totalCandidates) : 0
let avgExp = totalCandidates ? (totalExp / totalCandidates).toFixed(1) : "0"
document.getElementById("insightTotalCandidates").innerText = totalCandidates
document.getElementById("insightAvgScore").innerText = avgScore
document.getElementById("insightTopTalent").innerText = topTalent
document.getElementById("insightAvgExp").innerText = avgExp + "y"

let bestCandidate = [...currentResults].sort(compareCandidateRank)[0] || {}
let lowMatchCount = currentResults.filter(c => (c.final_score || 0) < 45).length
let roleTitle = document.getElementById("insightRoleTitle")
let decisionStatus = document.getElementById("insightDecisionStatus")
let decisionText = document.getElementById("insightDecisionText")
let bestName = document.getElementById("insightBestCandidate")
let bestScore = document.getElementById("insightBestScore")
let riskSignal = document.getElementById("insightRiskSignal")

if(roleTitle) roleTitle.innerText = (window.currentJobTitle || "Selected Role") + " Intelligence"
if(bestName) bestName.innerText = bestCandidate.full_name || bestCandidate.name || "No candidate"
if(bestScore) bestScore.innerText = "Score " + formatScore(candidateRecruiterScore(bestCandidate))
if(riskSignal) riskSignal.innerText = lowMatchCount + (lowMatchCount === 1 ? " low-match" : " low-match")

if(decisionStatus && decisionText){
    if(avgScore >= 70 || topTalent > 0){
        decisionStatus.innerText = "Shortlist-ready pool"
        decisionText.innerText = "Strong score signals are present. Prioritize the lead profiles and validate role-critical skills before outreach."
    }else if(avgScore >= 45){
        decisionStatus.innerText = "Recruiter review required"
        decisionText.innerText = "Candidate quality is mixed. Use score bands, skill supply, and experience mix before moving candidates forward."
    }else{
        decisionStatus.innerText = "Low-match candidate pool"
        decisionText.innerText = "The current pool needs manual validation or broader sourcing before shortlist decisions."
    }
}

/* SKILL CHART */

let sortedSkills = buildJdSkillCoverage(currentResults)
.sort((a,b)=>b[1]-a[1] || a[0].localeCompare(b[0]))
.slice(0,10)
let skillCountBox = document.getElementById("insightSkillCount")
if(skillCountBox) skillCountBox.innerText = sortedSkills.length + " JD skills"

insightCharts.skills = new Chart(document.getElementById("insightSkillChart"),{
type:"bar",
data:{
labels:sortedSkills.map(s=>s[0]),
datasets:[{
label:"Candidates with JD skill",
data:sortedSkills.map(s=>s[1]),
backgroundColor:"#2563eb",
borderRadius:8,
barThickness:14,
maxBarThickness:16,
categoryPercentage:.7,
barPercentage:.75
}]
},
options:{
responsive:true,
maintainAspectRatio:false,
indexAxis:"y",
layout:{
padding:{top:8,right:8,bottom:4,left:0}
},
plugins:{
legend:{display:false},
tooltip:{
displayColors:false,
callbacks:{
label:(context)=>`${context.raw || 0} candidate${Number(context.raw) === 1 ? "" : "s"} with this JD skill`
}
}
},
scales:{
x:{
beginAtZero:true,
grid:{color:"#eef2f7"},
suggestedMax:Math.max(1, totalCandidates),
ticks:{precision:0,font:{weight:"800"}, color:"#64748b"}
},
y:{
grid:{display:false},
ticks:{
font:{weight:"800", size:11},
color:"#334155",
padding:8,
autoSkip:false
}
}
}
}
})

/* EXPERIENCE */

insightCharts.exp = new Chart(document.getElementById("insightExpChart"),{

type:"doughnut",

data:{
labels:Object.keys(expBuckets),

datasets:[{
data:Object.values(expBuckets),

backgroundColor:[
"#6366f1",
"#22c55e",
"#f59e0b",
"#ef4444"
],

borderWidth:0
}]
},

options:{
responsive:true,
maintainAspectRatio:false,

plugins:{
legend:{
position:"bottom",
labels:{boxWidth:12,usePointStyle:true,font:{weight:"700"}}
}
},

cutout:"65%"
}

})

/* SCORE */

insightCharts.score = new Chart(document.getElementById("insightScoreChart"),{
type:"bar",

data:{
labels:["0-20","20-40","40-60","60-80","80-100"],

datasets:[{
label:"Score Distribution",
data:scoreBuckets,
backgroundColor:["#ef4444","#f59e0b","#06b6d4","#4f46e5","#22c55e"],
borderRadius:8,
barThickness:42
}]
},

options:{
responsive:true,
maintainAspectRatio:false,

plugins:{
legend:{display:false}
},

scales:{

x:{
grid:{
display:false
}
},

y:{
beginAtZero:true,
grid:{
color:"#eef2f7"
},
ticks:{precision:0}
}

}

}

})
/* EDUCATION */

renderEducationSignals(education, totalCandidates)
updateAISummary()

}
async function updateAISummary(){

if(!currentResults || currentResults.length === 0) return

let bestCandidate = [...currentResults]
.sort(compareCandidateRank)[0]

let box = document.getElementById("aiSummaryBox")

if(!box) return

let skillSignals = buildCandidateSkillSignals(bestCandidate || {})

let fallbackSummary = {
    candidate_name: bestCandidate?.full_name || "No Candidate",
    verdict: "Review candidate profile",
    overall_summary: "Stored resume and scoring signals are ready for recruiter review while the AI narrative is loading or unavailable.",
    profile_summary: `${bestCandidate?.full_name || "This candidate"} has ${bestCandidate?.total_experience_years || 0} years experience. Key resume skills include ${textList(skillSignals.candidateCoverage.slice(0, 10))}.`,
    jd_alignment: `Matched evidence: ${textList(skillSignals.matched)}. Skills to validate: ${textList(skillSignals.missing, "no major skill gap from stored data")}.`,
    evidence: [
        `Score: ${bestCandidate?.final_score || 0}`,
        `Education: ${bestCandidate?.education || "not listed"}`,
        `Location: ${bestCandidate?.location || "not listed"}`
    ],
    projects: Array.isArray(bestCandidate?.projects) && bestCandidate.projects.length
        ? bestCandidate.projects.map(project => typeof project === "string" ? project : `${project.name || "Project"}: ${project.description || ""}`)
        : ["Project evidence was not available in the current result payload."],
    risks: skillSignals.missing.length
        ? skillSignals.missing.map(skill => `Validate ${skill}`)
        : ["No major JD skill gap from stored data."],
    next_steps: ["Review resume evidence.", "Validate role-critical skills in screening."]
}

let renderPills = (items, emptyText, className = "") => {
    let clean = uniqueCleanList(items)
    if(!clean.length){
        return `<span class="ats-summary-empty">${safeHtml(emptyText)}</span>`
    }
    return clean.slice(0, 16).map(item=>`<span class="${className}">${safeHtml(item)}</span>`).join("")
}

let renderList = (items, emptyText) => {
    let clean = uniqueCleanList(items)
    return clean.length
    ? clean.slice(0, 6).map(item => `<li>${safeHtml(item)}</li>`).join("")
    : `<li>${safeHtml(emptyText)}</li>`
}

let renderSummary = (summary, loading = false) => {
    let evidence = Array.isArray(summary.evidence) ? summary.evidence : []
    let projects = Array.isArray(summary.projects) ? summary.projects : []
    let risks = Array.isArray(summary.risks) ? summary.risks : []
    let nextSteps = Array.isArray(summary.next_steps) ? summary.next_steps : []
    let currentSkillSignals = buildCandidateSkillSignals(bestCandidate || {})
    let rawMissingText = safeText(bestCandidate?.missing_skills).trim()
    let cleanedRisks = risks.filter(item => safeText(item).trim() !== rawMissingText)

    if(currentSkillSignals.missing.length){
        cleanedRisks = [
            ...currentSkillSignals.missing.map(skill => `Validate ${skill}`),
            ...cleanedRisks
        ]
    }else if(!cleanedRisks.length){
        cleanedRisks = ["No major JD skill gap from stored data."]
    }

    let statusLabel = loading ? "Generating with OpenAI" : (summary.generated ? "OpenAI generated" : "Stored-data fallback")
    let statusClass = loading ? "is-loading" : (summary.generated ? "is-generated" : "is-stored")
    let displayJdAlignment = `Matched evidence: ${textList(currentSkillSignals.matched)}. Skills to validate: ${textList(currentSkillSignals.missing, "no major skill gap from stored data")}.`

    box.innerHTML = `
    <div class="ats-ai-summary-status ${statusClass}">
        <span>${safeHtml(statusLabel)}</span>
        <strong>${safeHtml(summary.verdict || "Review candidate")}</strong>
    </div>
    <div class="ats-summary-grid">
        <article>
            <small>Best candidate</small>
            <strong>${safeHtml(summary.candidate_name || bestCandidate?.full_name || "No Candidate")}</strong>
        </article>
        <article>
            <small>Score</small>
            <strong>${safeHtml(bestCandidate?.final_score || 0)}</strong>
        </article>
        <article>
            <small>Experience</small>
            <strong>${safeHtml(bestCandidate?.total_experience_years || 0)} years</strong>
        </article>
    </div>
    <div class="ats-ai-profile-card">
        <section class="ats-ai-narrative">
            <h4>Recruiter Snapshot</h4>
            <p>${safeHtml(summary.profile_summary || summary.overall_summary || "")}</p>
            <p>${safeHtml(displayJdAlignment)}</p>
            <p>${safeHtml(summary.overall_summary || "")}</p>
        </section>
        <section class="ats-ai-skill-card">
            <div class="ats-ai-skill-row">
                <span>Matched evidence</span>
                <div class="ats-summary-pills is-match">
                    ${renderPills(currentSkillSignals.matched, "No matched skills listed.", "is-match")}
                </div>
            </div>
            <div class="ats-ai-skill-row">
                <span>Skills to validate</span>
                <div class="ats-summary-pills is-gap">
                    ${renderPills(currentSkillSignals.missing, "No major JD skill gap.", "is-gap")}
                </div>
            </div>
        </section>
    </div>
    <div class="ats-ai-summary-lists">
        <article>
            <h4>Resume Evidence</h4>
            <ul>${renderList(evidence, "No evidence available.")}</ul>
        </article>
        <article>
            <h4>Projects / Work Examples</h4>
            <ul>${renderList(projects, "No project evidence available.")}</ul>
        </article>
        <article>
            <h4>Risks To Validate</h4>
            <ul>${renderList(cleanedRisks, "No risks listed.")}</ul>
        </article>
        <article>
            <h4>Next Steps</h4>
            <ul>${renderList(nextSteps, "Review candidate before outreach.")}</ul>
        </article>
    </div>
    `
}

renderSummary(fallbackSummary, true)

try{
    let jobId = window.currentJobId || bestCandidate?.job_id
    let resumeId = bestCandidate?.resume_id || bestCandidate?.id
    if(!jobId || !resumeId){
        renderSummary(fallbackSummary)
        return
    }

    let res = await fetch(API + "/ai-hiring-recommendation/" + encodeURIComponent(jobId) + "?resume_id=" + encodeURIComponent(resumeId))
    let summary = await res.json()
    if(!res.ok || summary.error || summary.detail){
        renderSummary(fallbackSummary)
        return
    }
    renderSummary(summary)
}catch(err){
    renderSummary(fallbackSummary)
}
}




// NAV ACTIVE BUTTON

document.addEventListener("DOMContentLoaded", () => {

bindJDAutofill()

document.querySelectorAll(".nav-btn").forEach(btn => {

btn.addEventListener("click", function(){

document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"))
this.classList.add("active")

})

})

setTimeout(()=>{
loadShortlistedCandidates()
},300)

})
// ---------------- COPY APPLY LINK ----------------

function copyApplyLink(){

let input=document.getElementById("applyLinkInput")

input.select()

document.execCommand("copy")

alert("Apply link copied")

}

async function loadDashboard(force=false){
let now = Date.now()
if(dashboardLoadPromise) return dashboardLoadPromise
if(!force && now - lastDashboardLoadAt < 1500) return Promise.resolve()

let table = document.getElementById("dashboardJobTable")
if(table && !dashboardJobs.length && !table.children.length){
table.innerHTML = `
<tr>
<td colspan="5" class="p-4 text-center text-gray-500">Loading jobs...</td>
</tr>
`
}

dashboardLoadPromise = (async()=>{
lastDashboardLoadAt = Date.now()
let res = await fetch(API + "/jobs", {
    headers: authHeaders()
})
let jobs = await res.json()

dashboardJobs = Array.isArray(jobs) ? jobs : []

document.getElementById("dash_active_jobs").innerText =
dashboardJobs.filter(j => j.is_active !== false).length

let totalApplicants = 0
let topScore = 0
let totalScore = 0
let scoreCount = 0

if(!table) return

table.innerHTML=""

let activeJobs = dashboardJobs.filter(job => job.is_active !== false)

if(activeJobs.length === 0){
table.innerHTML = `
<tr>
<td colspan="5" class="p-4 text-center text-gray-500">No active jobs yet</td>
</tr>
`
}

activeJobs.forEach(job=>{

totalApplicants += job.total_applicants || 0

if(job.top_score > topScore){
topScore = job.top_score
}

totalScore += job.top_score || 0
scoreCount++

table.innerHTML += `

<tr class="ats-job-row">

<td class="ats-job-name-cell">

<input 
type="checkbox"
class="jobFilterCheckbox ats-job-checkbox"
value="${job.id}"
onchange="updateDashboardCards()"
>

<span class="ats-job-avatar">JD</span>
<span class="ats-job-copy">
<span class="ats-ellipsis ats-job-title" title="${safeHtml(job.job_title)}">
${safeHtml(job.job_title)}
</span>
<small>Screening pipeline ready</small>
</span>

</td>

<td class="ats-job-metric-cell">
<span class="ats-job-metric">${job.total_applicants || 0}</span>
</td>

<td class="ats-job-metric-cell">
<span class="ats-job-score">${job.top_score || 0}</span>
</td>

<td class="ats-job-status-cell">
<span class="ats-job-status">Active</span>
</td>

<td class="ats-job-actions-cell">

<button
onclick="openJobResult('${safeJs(job.id)}','${safeJs(job.job_title)}')"
class="ats-table-action ats-table-action-view">

View

</button>

<button
onclick="openTopCandidate('${safeJs(job.id)}','${safeJs(job.job_title)}')"
class="ats-table-action ats-table-action-top">

Top Candidate

</button>

<button
onclick="openJobPostKit('${safeJs(job.id)}')"
class="ats-table-action ats-table-action-posts">

Posts

</button>

<button
onclick="configureJobResumeFolder('${safeJs(job.id)}')"
class="ats-table-action ats-table-action-folder"
title="${safeHtml(job.resume_folder_path ? `Folder: ${job.resume_folder_path}` : "Configure resume folder")}">

Folder

</button>

<button
onclick="deactivateJob('${safeJs(job.id)}')"
class="ats-table-action ats-table-action-danger">

Deactivate

</button>

</td>

</tr>

`

})

document.getElementById("dash_total_applicants").innerText = totalApplicants
document.getElementById("dash_top_score").innerText = topScore

let avg = scoreCount ? Math.round(totalScore/scoreCount) : 0
document.getElementById("dash_avg_score").innerText = avg

updateDashboardCards()

loadTopCandidate()

})()

try{
await dashboardLoadPromise
}finally{
dashboardLoadPromise = null
}
}
async function deactivateJob(jobId){


    if(!jobId){
        return;
    }

    if(!confirm("Deactivate this job?")) return;

    try {

        const res = await fetch(API + "/deactivate-job/" + jobId, {
            method: "PUT"
        });


        const data = await res.json();

        alert("Job deactivated");

        // * UI refresh
        loadDashboard(true);
        loadEditJobs();
        loadApplyJobs();

    } catch (err) {
    }
}

function updateDashboardCards(){

let checkboxes = document.querySelectorAll(".jobFilterCheckbox:checked")

let selectedIds = [...checkboxes].map(c=>c.value)

let jobsToCalculate=[]

if(selectedIds.length===0){
jobsToCalculate = dashboardJobs.filter(j => j.is_active !== false)
}else{
jobsToCalculate = dashboardJobs.filter(j=>j.is_active !== false && selectedIds.includes(j.id))
}

let totalApplicants=0
let topScore=0
let totalScore=0
let count=0

jobsToCalculate.forEach(job=>{

totalApplicants += job.total_applicants || 0

if(job.top_score > topScore){
topScore = job.top_score
}

totalScore += job.top_score || 0
count++

})

let avg = count ? Math.round(totalScore/count) : 0

document.getElementById("dash_total_applicants").innerText = totalApplicants
document.getElementById("dash_top_score").innerText = topScore
document.getElementById("dash_avg_score").innerText = avg
renderJobChart(jobsToCalculate)
renderApplicationsBySource(aggregateSourceCounts(jobsToCalculate))

}

async function configureJobResumeFolder(jobId){
let job = (dashboardJobs || []).find(item => String(item.id) === String(jobId)) || {}
let currentPath = job.resume_folder_path || ""
let folderPath = prompt("Paste the local resume folder path for this job. New PDF, DOCX, or TXT resumes in this folder will be treated as applications.", currentPath)
if(folderPath === null) return
folderPath = folderPath.trim()
if(!folderPath){
alert("Folder path is required.")
return
}

try{
let saveRes = await fetch(API + "/jobs/" + encodeURIComponent(jobId) + "/resume-folder", {
method:"POST",
headers:{
...authHeaders(),
"Content-Type":"application/json"
},
body:JSON.stringify({folder_path: folderPath})
})
let saveData = await saveRes.json().catch(()=>({}))
if(!saveRes.ok){
alert(saveData.detail || saveData.error || "Could not configure resume folder.")
return
}

let syncRes = await fetch(API + "/jobs/" + encodeURIComponent(jobId) + "/resume-folder/sync", {
method:"POST",
headers:authHeaders()
})
let syncData = await syncRes.json().catch(()=>({}))
if(!syncRes.ok){
alert(syncData.detail || syncData.error || "Folder saved, but sync failed.")
return
}

alert(`Resume folder synced.\nScanned: ${syncData.scanned || 0}\nImported: ${syncData.imported || 0}\nSkipped: ${syncData.skipped || 0}\nFailed: ${syncData.failed || 0}`)
await loadJobs()
if(typeof loadDashboard === "function"){
loadDashboard()
}
}catch(error){
alert("Could not configure or sync resume folder.")
}
}

function aggregateSourceCounts(jobs){
let counts = {linkedin:0, whatsapp:0, naukri:0, referral:0, website:0, direct:0, folder:0, unknown:0}
;(Array.isArray(jobs) ? jobs : []).forEach(job => {
let sourceCounts = job.applications_by_source || {}
Object.keys(counts).forEach(source => {
counts[source] += Number(sourceCounts[source] || 0)
})
})
return counts
}

function renderApplicationsBySource(counts){
let container = document.getElementById("applicationsBySourceCard")
if(!container) return

let labels = {
linkedin:"LinkedIn",
whatsapp:"WhatsApp",
naukri:"Naukri",
referral:"Referral",
website:"Website",
direct:"Direct",
folder:"Resume Folder",
unknown:"Unknown"
}
let sourceMeta = {
linkedin:{abbr:"IN", color:"#2563eb"},
whatsapp:{abbr:"WA", color:"#16a34a"},
naukri:{abbr:"NK", color:"#7c3aed"},
referral:{abbr:"RF", color:"#f59e0b"},
website:{abbr:"WB", color:"#0891b2"},
direct:{abbr:"DR", color:"#0f766e"},
folder:{abbr:"FL", color:"#4f46e5"},
unknown:{abbr:"UN", color:"#64748b"}
}
let total = Object.values(counts || {}).reduce((sum, value) => sum + Number(value || 0), 0)
if(!total){
container.innerHTML = `
<div class="ats-source-empty">
<div class="ats-source-empty-icon">SO</div>
<strong>No source data yet</strong>
<span>Share tracked links or sync a resume folder to start seeing source movement.</span>
</div>
`
return
}

let rows = Object.keys(labels).map(source => {
let count = Number(counts[source] || 0)
let pct = total ? Math.round((count / total) * 100) : 0
return {source, count, pct, label:labels[source], meta:sourceMeta[source]}
})
let activeRows = rows.filter(row => row.count > 0)
let top = activeRows.slice().sort((a,b)=>b.count-a.count)[0] || rows[0]

container.innerHTML = `
<div class="ats-source-summary">
<div class="ats-source-total">
<span>Total</span>
<strong>${total}</strong>
</div>
<div class="ats-source-leader">
<span>Top source</span>
<strong>${safeHtml(top.label)}</strong>
<small>${top.count} applicants | ${top.pct}%</small>
</div>
</div>
<div class="ats-source-list">
${rows.map(row => {
let isEmpty = row.count <= 0
return `
<div class="ats-source-row ${isEmpty ? "is-empty" : ""}" style="--source-color:${row.meta.color};--source-pct:${row.pct}%;">
<span class="ats-source-icon">${safeHtml(row.meta.abbr)}</span>
<div class="ats-source-main">
<div class="ats-source-label-line">
<strong>${safeHtml(row.label)}</strong>
<span>${row.pct}%</span>
</div>
<div class="ats-source-bar"><i></i></div>
</div>
<b>${row.count}</b>
</div>
`
}).join("")}
</div>
`
}

async function loadApplicationsBySource(){
try{
let res = await fetch(API + "/analytics/applications-by-source", { headers: authHeaders() })
let counts = await res.json()
if(res.ok && counts && !counts.detail){
renderApplicationsBySource(counts)
return
}
}catch(error){}
renderApplicationsBySource(aggregateSourceCounts(dashboardJobs.filter(j => j.is_active !== false)))
}



function renderJobChart(jobs){

jobs = (Array.isArray(jobs) ? jobs : []).filter(j => j.is_active !== false)

let canvas = document.getElementById("jobApplicationChart")

if(!canvas) return

let container = canvas.parentElement
if(!container) return

let titleCounts = {}
jobs.forEach(job => {
let title = safeText(job.job_title || "Untitled Job").trim() || "Untitled Job"
let key = title.toLowerCase()
titleCounts[key] = (titleCounts[key] || 0) + 1
})

let seenTitles = {}
let chartJobs = jobs.map(job => {
let title = safeText(job.job_title || "Untitled Job").trim() || "Untitled Job"
let key = title.toLowerCase()
seenTitles[key] = (seenTitles[key] || 0) + 1

return {
title:titleCounts[key] > 1 ? `${title} #${seenTitles[key]}` : title,
applicants:Number(job.total_applicants || 0),
topScore:Number(job.top_score || 0)
}
})

if(!chartJobs.length){
chartJobs = [{title:"No active jobs",applicants:0,topScore:0}]
}

if(jobChart){
jobChart.destroy()
jobChart = null
}

canvas.style.display = "none"
let existing = container.querySelector(".ats-job-volume-widget")
if(existing) existing.remove()

let total = chartJobs.reduce((sum, item)=>sum + Number(item.applicants || 0), 0)
let top = chartJobs.slice().sort((a,b)=>b.applicants-a.applicants)[0] || chartJobs[0]
let maxValue = Math.max(...chartJobs.map(item => Number(item.applicants || 0)), 1)

let widget = document.createElement("div")
widget.className = "ats-job-volume-widget"
widget.innerHTML = `
<div class="ats-job-volume-summary">
<div class="ats-job-volume-total">
<span>Total Applicants</span>
<strong>${total}</strong>
</div>
<div class="ats-job-volume-leader">
<span>Leading Role</span>
<strong>${safeHtml(top.title)}</strong>
<small>${top.applicants || 0} applicants${top.topScore ? " | top score " + formatScore(top.topScore) : ""}</small>
</div>
</div>
<div class="ats-job-volume-list">
${chartJobs.map((job, index) => {
let pct = Math.round((Number(job.applicants || 0) / maxValue) * 100)
let score = Number(job.topScore || 0)
return `
<article class="ats-job-volume-row ${Number(job.applicants || 0) ? "" : "is-empty"}" style="--job-pct:${pct}%;--job-index:${index};">
<div class="ats-job-volume-top">
<div>
<strong title="${safeHtml(job.title)}">${safeHtml(shortText(job.title, 34))}</strong>
<span>${score ? `Top score ${safeHtml(formatScore(score))}` : "No score yet"}</span>
</div>
<b>${job.applicants || 0}</b>
</div>
<div class="ats-job-volume-track"><i></i></div>
</article>
`
}).join("")}
</div>
`
container.appendChild(widget)

}

async function loadTopCandidate(){

let res = await fetch(API + "/top-candidate")
let data = await res.json()

let box = document.getElementById("dash_top_candidate")

if(!box) return

if(!data.name){
box.innerText = "No Data"
return
}

box.innerHTML = `
${data.name}<br>
<span style="font-size:12px">
Score: ${data.score}
</span>
`


}

async function openTopCandidate(jobId,jobTitle){

let dash = document.getElementById("dashboardPage")
let page = document.getElementById("candidateProfilePage")
let content = document.getElementById("candidateProfileContent")

if(dash) dash.classList.add("hidden")
if(page) page.classList.remove("hidden")

let cleanJobTitle = safeText(jobTitle).trim() || "Job"
setCandidateProfileHeader(
cleanJobTitle + " - Top Candidate",
"Review the highest ranked applicant for this job with fit signals, contact details, and hiring notes.",
"Back to Dashboard",
"showPage('dashboard')"
)

if(content){
content.innerHTML = `
<div class="ats-candidate-loading">
<div></div>
<span>Loading top candidate profile...</span>
</div>
`
}

try{
let res = await fetch(API + "/results/" + jobId)
let data = await res.json()


let results = []

if(Array.isArray(data)){
results = data
}else if(data.results){
results = data.results
}

if(results.length === 0){
content.innerHTML = `
<div class="ats-candidate-empty">
<div>NO</div>
<h3>No candidates found</h3>
<p>There are no applicants attached to this job yet. Once resumes are analyzed, the best match will appear here.</p>
<button onclick="showPage('dashboard')" class="ats-back-btn">Back to Dashboard</button>
</div>
`
return
}

let top = results.sort(compareCandidateRank)[0]
registerCandidateProfile(top)
let score = Number(top.final_score) || 0
let band = scoreBand(score, top)
let skills = normalizeList(top.key_skills)
let displayName = candidateSafeDisplay(top, "name", "Needs manual review")
let displayEmail = candidateSafeDisplay(top, "email", "Needs manual review")
let displayLocation = candidateSafeDisplay(top, "location", "Needs manual review")
let education = safeText(candidateSafeDisplay(top, "education", "Needs manual review"))
let experience = candidateSafeDisplay(top, "experience", "Needs manual review")
let status = getStatus(score)
let alreadyShortlisted = safeText(top.status).toLowerCase().includes("shortlist")
let showReparse = top.resume_available !== false && candidateProfileNeedsReparse(top)

content.innerHTML = `
<section class="ats-candidate-profile-grid">
<div class="ats-candidate-left-column">
<div class="ats-candidate-hero-panel">
<div class="ats-candidate-hero-top">
<div class="ats-candidate-avatar-large">${safeHtml(candidateInitials(top.full_name))}</div>
<div class="ats-candidate-main-copy">
<span class="ats-fit-pill ${band.className}">${safeHtml(band.label)}</span>
<h3>${safeHtml(displayName)}</h3>
<p>${safeHtml(top.designation || cleanJobTitle)}</p>
</div>
</div>

${candidateQaActions(top, top.resume_id, showReparse)}

<div class="ats-candidate-score-wrap">
<div class="ats-score-ring" style="--score:${Math.min(Math.max(score,0),100)}">
<strong>${safeHtml(formatScore(score))}</strong>
<span>AI score</span>
</div>
<div>
<h4 id="topCandidateProfileStatus">${safeHtml(alreadyShortlisted ? "Shortlisted" : status)}</h4>
<p>Highest ranked profile for this job based on AI fit score, resume signals, and role relevance.</p>
</div>
</div>

<div class="ats-candidate-primary-actions">
<button onclick="shortlistTopCandidate('${safeJs(top.resume_id)}','${safeJs(jobId)}')" class="ats-candidate-action is-shortlist ${alreadyShortlisted ? "is-done" : ""}" ${alreadyShortlisted ? "disabled" : ""}>${alreadyShortlisted ? "Shortlisted" : "Shortlist Candidate"}</button>
<a href="mailto:${safeHtml(top.email || "")}" class="ats-candidate-action ${top.email ? "" : "is-disabled"}">Email Candidate</a>
<a href="tel:${safeHtml(top.phone || "")}" class="ats-candidate-action is-secondary ${top.phone ? "" : "is-disabled"}">Call</a>
</div>
</div>

${topCandidateSkillCoverage(top)}
</div>

<div class="ats-candidate-right-column">
<div class="ats-candidate-summary-panel">
<h4>Candidate Snapshot</h4>
<div class="ats-candidate-detail-grid">
${topCandidateDetail("Email", displayEmail)}
${topCandidateDetail("Phone", candidateSafeDisplay(top, "phone", "Needs manual review"))}
${topCandidateDetail("Location", displayLocation)}
${topCandidateDetail("Experience", experience)}
${topCandidateDetail("Last Company", candidateSafeDisplay(top, "last_company", "Needs manual review"))}
${topCandidateDetail("Education", education)}
</div>
</div>

<div class="ats-candidate-panel ats-candidate-skills-panel">
<div class="ats-panel-title-row">
<div>
<h4>Skills Match</h4>
<p>Extracted from the candidate resume.</p>
</div>
<span>${skills.length} skills</span>
</div>
<div class="ats-skill-cloud">
${topCandidateSkillPills(skills)}
</div>
</div>

<div class="ats-candidate-panel ats-candidate-projects-panel">
<div class="ats-panel-title-row">
<div>
<h4>Project Evidence</h4>
<p>Resume projects and work examples used for screening context.</p>
</div>
<span>Resume proof</span>
</div>
<div id="topCandidateProjects">
${top.projects ? topCandidateProjectEvidence(top.projects) : topCandidateProjectEvidence(null, true)}
</div>
</div>
</div>

<div class="ats-candidate-panel ats-candidate-ai-panel">
<div class="ats-panel-title-row">
<div>
<h4>AI Recommendation</h4>
<p id="topCandidateAiSummary">Generating a JD-based screening summary with candidate evidence.</p>
</div>
<span id="topCandidateAiStatus">${safeHtml(alreadyShortlisted ? "Shortlisted" : status)}</span>
</div>
<ul id="topCandidateAiList" class="ats-recommendation-list">
${topCandidateRecommendation(score, null, true)}
</ul>
</div>
</section>
`
loadTopCandidateRecommendation(jobId, top.resume_id, score)
}catch(error){
content.innerHTML = `
<div class="ats-candidate-empty">
<div>ERR</div>
<h3>Could not load candidate</h3>
<p>Please try again after checking the API connection.</p>
<button onclick="showPage('dashboard')" class="ats-back-btn">Back to Dashboard</button>
</div>
`
}

}

function getStatus(score){

if(score >= 65){
return "Shortlisted"
}

if(score >= 50){
return "Review"
}

return "Rejected"

}

function toggleColumnPanel(){

let panel = document.getElementById("columnPanel")

if(panel.style.display === "none" || panel.style.display === ""){
panel.style.display = "block"
}else{
panel.style.display = "none"
}

}


function toggleColumn(checkbox){

    let col = parseInt(checkbox.dataset.col)

    let table = document.querySelector("#jobResultPage table")

    let headers = table.querySelectorAll("thead th")
    let rows = table.querySelectorAll("tbody tr")

    // HEADER
    if(headers[col]){
        if(checkbox.checked){
            headers[col].classList.remove("hidden")
        }else{
            headers[col].classList.add("hidden")
        }
    }

    // BODY
    rows.forEach(row => {

        let cell = row.children[col]

        if(cell){
            if(checkbox.checked){
                cell.classList.remove("hidden")
            }else{
                cell.classList.add("hidden")
            }
        }

    })
}

function formatExperience(exp){

  if(!exp) return "0 year"

  let years = Math.floor(exp)

  if(exp < 1){
    return "0-1 year"
  }

  if(exp - years > 0.5){
    return years + "+ years"
  }

  return years + " year"
}

function formatSkills(skills){

if(!skills) return ""

let arr = Array.isArray(skills)
? skills
: safeText(skills).split(",")

return arr.map(s =>
`<span style="
background:#eef2ff;
color:#4338ca;
padding:3px 8px;
border-radius:6px;
font-size:12px;
margin:2px;
display:inline-block;">
${safeHtml(safeText(s).trim())}
</span>`
).join("")

}

function formatScore(score){

if(!score) return "0"

return Number(score).toFixed(1)

}


function formatPercent(p){

if(!p) return "0%"

return Number(p).toFixed(1) + "%"

}

function formatEducation(edu){

if(!edu) return ""

try{

// string -> object
if(typeof edu === "string"){

try{
edu = JSON.parse(edu)
}catch{
return edu
}

}

// single object -> array
if(!Array.isArray(edu) && typeof edu === "object"){
edu = [edu]
}

if(Array.isArray(edu)){

return edu.map(e=>{

let degree = e.degree || ""
let field = e.field || ""
let college = e.institution || ""
let start = e.start_date || ""
let end = e.end_date || ""

return `
<div style="line-height:1.4">
<b>${degree}${field ? " - " + field : ""}</b><br>
<span style="color:#6b7280;font-size:12px">
${college}${start || end ? " ("+start+" - "+end+")" : ""}
</span>
</div>
`

}).join("")

}

}catch(err){


}

return ""

}

function formatLocation(loc){

if(!loc) return ""

return loc.replace(/,/g,", ")

}

function toggleTop10ColumnPanel(){

let panel=document.getElementById("top10ColumnPanel")

panel.style.display =
panel.style.display==="none" ? "block" : "none"

}

function toggleTop10Column(checkbox){

let col=checkbox.dataset.col

let table=document.getElementById("top10AnalyzerTable")

for(let row of table.rows){

let cell=row.cells[col]

if(cell){
cell.style.display=checkbox.checked ? "" : "none"
}

}

}


async function generateAIExplanation(index){

let candidate = bulkResults[index]

let text = `
Candidate: ${candidate.full_name}

Experience: ${candidate.total_experience_years} years

Skill Match: ${candidate.skill_match_percent}%

Score: ${candidate.final_score}

Reason: Strong match with job description and relevant skills.
`

alert(text)

}

function openCandidateAIProfile(index){

let candidate = bulkResults[index]

if(!candidate){
alert("Candidate data not found")
return
}

document.getElementById("bulkTop10").classList.add("hidden")
document.getElementById("candidateAIProfilePage").classList.remove("hidden")
let backTop10Button = document.getElementById("candidateAIBackTop10")
if(backTop10Button) backTop10Button.classList.remove("hidden")

let html = `

<h3 class="text-xl font-semibold mb-4">${candidate.full_name || "N/A"}</h3>

<p><b>Email:</b> ${candidate.email || "N/A"}</p>
<p><b>Phone:</b> ${candidate.phone || "N/A"}</p>
<p><b>Location:</b> ${candidate.location || "N/A"}</p>

<hr class="my-4">

<p><b>Experience:</b> ${candidate.total_experience_years || 0} years</p>
<p><b>Industry:</b> ${candidate.industry || "N/A"}</p>
<p><b>Domain:</b> ${candidate.domain || "N/A"}</p>
<p><b>Education:</b> ${formatEducation(candidate.education)}</p>

<hr class="my-4">

<h4 class="font-semibold">Matched Skills</h4>
<p>${safeHtml(textList(cleanedCandidateMatchedSkills(candidate), "None"))}</p>

<h4 class="font-semibold mt-4">Missing Skills</h4>
<p>${safeHtml(textList(cleanedCandidateMissingSkills(candidate), "None"))}</p>

<hr class="my-4">

<h4 class="font-semibold">AI Analysis</h4>

<p>
Skill Match: ${candidate.skill_match_percent || 0}% <br>
Semantic Score: ${candidate.semantic_score || 0} <br>
Final Score: ${candidate.final_score || 0}
</p>

`

document.getElementById("candidateAIContent").innerHTML = html

}

function backToTop10(){

document.getElementById("candidateAIProfilePage").classList.add("hidden")
document.getElementById("bulkTop10").classList.remove("hidden")
let backTop10Button = document.getElementById("candidateAIBackTop10")
if(backTop10Button) backTop10Button.classList.add("hidden")

window.scrollTo({top:0,behavior:"smooth"})

}

function checkLogin(){
if(typeof completeOAuthLogin === "function"){
    completeOAuthLogin()
}

let token = localStorage.getItem("token")
let expired = typeof isTokenExpired === "function" ? isTokenExpired(token) : false

if(!token || expired){
    localStorage.removeItem("token")
    localStorage.removeItem("username")
    window.location.href = "login.html"
    return
}

let profile = document.getElementById("profileName")
if(profile){
    profile.innerText = localStorage.getItem("username") || "Recruiter"
}
updateGmailConnectStatus()
restoreBulkSessionFromStorage()
}

function connectGmailForOutreach(){
    if(typeof completeOAuthLogin === "function"){
        completeOAuthLogin()
    }

    let token = localStorage.getItem("token")
    if(!token){
        alert("Please login first before connecting Gmail.")
        return
    }

    let loginEmail = getRecruiterEmailFromSession()
    let email = getReplySyncEmail()
    if(!email || !email.includes("@")){
        alert("Please enter a valid inbox email first.")
        document.getElementById("outreachSenderEmail")?.focus()
        return
    }
    localStorage.setItem("outreachSenderEmail", email)
    localStorage.setItem("oauthReturnPage", window.currentJobId ? "communicationResults" : "communication")
    if(window.currentJobId) localStorage.setItem("oauthReturnJobId", window.currentJobId)
    if(window.currentJobTitle) localStorage.setItem("oauthReturnJobTitle", window.currentJobTitle)

    window.location.href = API + "/gmail-connect?email=" + encodeURIComponent(email) + "&app_email=" + encodeURIComponent(loginEmail)
}

function updateGmailConnectStatus(){
    let status = document.getElementById("gmailConnectStatus")
    let preview = document.getElementById("activeSenderPreview")
    if(!status && !preview) return
    let input = document.getElementById("outreachSenderEmail")
    let config = readOutreachSenderConfig()
    let saved = getReplySyncEmail()
    if(input && saved && !safeText(input.value).trim()) input.value = saved
    let email = getReplySyncEmail() || "your inbox"
    let connectedEmail = safeText(localStorage.getItem("gmailConnectedEmail")).trim().toLowerCase()
    let isConnected = localStorage.getItem("gmailConnected") === "true" && (!connectedEmail || connectedEmail === email.toLowerCase())
    if(config.mode === "own_domain" && config.verification_status === "verified"){
        if(status) status.innerText = "Own domain sender is verified and active. Reply sync remains separate."
        if(preview) preview.innerHTML = `<span>Active sender</span><strong>${safeHtml(config.sender_name || config.from_name || "Recruiting Team")} &lt;${safeHtml(config.from_email)}&gt;</strong><small>Reply-To: ${safeHtml(config.from_email)}</small>`
    }else if(config.mode === "own_domain"){
        if(status) status.innerText = "Your own domain is pending DNS verification. Use HireScore AI sender until it is verified."
        if(preview) preview.innerHTML = `<span>Pending sender</span><strong>${safeHtml(config.sender_name || config.from_name || "Recruiting Team")} &lt;${safeHtml(config.from_email || "sender@company.com")}&gt;</strong><small>Verification status: ${safeHtml(config.verification_status || "pending")}</small>`
    }else{
        if(status) status.innerText = isConnected
            ? "HireScore AI sender is active. Google/Workspace reply sync is connected for " + email + "."
            : "HireScore AI sender is active. Connect reply sync separately when you want candidate replies tracked."
        if(preview) preview.innerHTML = `<span>Active sender</span><strong>${HIRE_SCORE_DEFAULT_FROM_NAME} &lt;${HIRE_SCORE_DEFAULT_FROM_EMAIL}&gt;</strong><small>Reply-To: ${safeHtml(config.reply_to || email || "recruiter@email.com")}</small>`
    }
}

async function syncGmailReplies(options = {}){
    let silent = options.silent === true
    let reload = options.reload !== false

    if(!window.currentJobId){
        if(!silent) alert("Open a communication job first.")
        return
    }

    let recruiterEmail = getReplySyncEmail()
    if(!recruiterEmail){
        let token = localStorage.getItem("token")
        let payload = typeof parseJwt === "function" ? parseJwt(token) : null
        recruiterEmail = payload?.email || ""
    }

    if(!recruiterEmail){
        if(!silent) alert("Recruiter email not found. Please login again.")
        return
    }

    let button = !silent && typeof event !== "undefined" ? event.target : null
    setButtonLoading(button, true, "Syncing...")

    try{
        let res = await fetch(API + "/sync-gmail-responses", {
            method:"POST",
            headers:{
                "Content-Type":"application/json",
                "Authorization":"Bearer " + localStorage.getItem("token")
            },
            body:JSON.stringify({
                job_id: window.currentJobId,
                recruiter_email: recruiterEmail
            })
        })
        let data = await res.json()
        if(!res.ok){
            if(!silent) alert(data.detail || "Gmail sync failed")
            return
        }
        if(!silent) alert("Gmail replies synced. Updated: " + (data.updated || 0))
        if(reload) await loadCommunicationSplit(window.currentJobId)
        return data
    }catch(err){
        if(!silent) alert("Gmail sync failed")
    }finally{
        setButtonLoading(button, false)
    }
}

async function updateCommunicationResponse(candidateId, responseStatus){
    if(!candidateId || !responseStatus){
        alert("Candidate response update missing data.")
        return
    }

    let trigger = typeof event !== "undefined" ? event.currentTarget : null
    setButtonLoading(trigger, true, "Saving...")

    try{
        let res = await fetch(API + "/communication-response", {
            method:"POST",
            headers: authHeaders(),
            body:JSON.stringify({
                candidate_id: candidateId,
                response_status: responseStatus
            })
        })

        let data = await res.json()
        if(!res.ok){
            alert(data.detail || "Could not update candidate response")
            return
        }

        await loadCommunicationSplit(window.currentJobId)
    }catch(err){
        alert("Could not update candidate response")
    }finally{
        setButtonLoading(trigger, false)
    }
}

async function dropCommunicationCandidate(candidateId, jobId){
    if(!candidateId){
        alert("Candidate is missing.")
        return
    }

    if(!confirm("Drop this candidate from the ATS database views?")){
        return
    }

    let trigger = typeof event !== "undefined" ? event.currentTarget : null
    setButtonLoading(trigger, true, "Dropping...")

    try{
        let res = await fetch(API + "/drop-candidate/" + encodeURIComponent(candidateId), {
            method: "POST",
            headers: authHeaders()
        })

        let data = await res.json()
        if(!res.ok || data.error){
            alert("Could not drop candidate: " + (data.detail || data.error || "Unknown error"))
            return
        }

        await loadCommunicationSplit(jobId || window.currentJobId)
    }catch(err){
        alert("Could not drop candidate")
    }finally{
        setButtonLoading(trigger, false)
    }
}

async function loadJobFilters(){

let res = await fetch(API+"/jobs", {
    headers: authHeaders()
})

let jobs = await res.json()

let filterBox = document.getElementById("jobFilterBox")
let scoreBox = document.getElementById("shortlistScoreBox")

if(!filterBox || !scoreBox) return

filterBox.innerHTML=""
scoreBox.innerHTML=""

jobs
.filter(job => job.is_active === true)
.forEach(job=>{

// JOB FILTER CHECKBOX

filterBox.innerHTML += `

<label>

<input type="checkbox"
class="jobFilterCheckbox"
value="${job.id}"
checked
onchange="loadShortlistedCandidates()">

${job.job_title}

</label><br>

`

// SHORTLIST SCORE CONFIG

scoreBox.innerHTML += `

<div class="flex justify-between">

<span>${job.job_title}</span>

<input type="number"
value="${job.shortlist_score || 60}"
data-job="${job.id}"
onchange="loadShortlistedCandidates()"
class="border p-1 rounded w-16 shortlistScoreInput">

</div>

`

})

}

function getSelectedJobs(){

let jobSelect = document.getElementById("shortlistJobSelect")

if(jobSelect && jobSelect.value){
return [String(jobSelect.value)]
}

return []

}

function toggleShortlistColumn(checkbox){

let col = parseInt(checkbox.dataset.col)

let table = document.getElementById("shortlistTableMain")

if(!table) return

let headers = table.querySelectorAll("thead th")
let rows = table.querySelectorAll("tbody tr")

// HEADER
if(headers[col]){

if(checkbox.checked){
headers[col].classList.remove("hidden")
}else{
headers[col].classList.add("hidden")
}

}

// BODY
rows.forEach(row=>{

let cell = row.children[col]

if(!cell) return

if(checkbox.checked){
cell.classList.remove("hidden")
}else{
cell.classList.add("hidden")
}

})

}

async function loadShortlistedCandidatesLegacy(){

    let jobId = document.getElementById("shortlistJobSelect").value

    if(!jobId){
        return
    }

    let res = await fetch(API + "/shortlisted?job_id=" + jobId)
    let data = await res.json()

    let selectedJobs = getSelectedJobs()

    let minScoreInput = document.getElementById("shortlistMinScore")

    // * DEFAULT LOGIC (MOST IMPORTANT FIX)
    let minScore = (minScoreInput && minScoreInput.value)
        ? Number(minScoreInput.value)
        : 0

    let table = document.getElementById("shortlistTable")

    if(!table) return

    table.innerHTML = ""

    // NO JOB SELECTED
    if(selectedJobs.length === 0){

        table.innerHTML = `
        <tr>
            <td colspan="18" style="text-align:center;padding:20px;color:#6b7280">
                Select a job to view shortlisted candidates
            </td>
        </tr>
        `

        return
    }

    let count = 0

    data.forEach((c, i) => {

        let score = c.score || c.final_score || 0

        // * FILTER
        if(score < minScore){
            return
        }

        count++
        let profileName = candidateProfileNameButton({
            ...c,
            full_name: c.name || c.full_name,
            name: c.name || c.full_name,
            final_score: score,
            total_experience_years: c.total_experience_years ?? c.experience,
            last_company_name: c.last_company_name || c.last_company
        }, "ats-candidate-name-link ats-shortlist-name-link")

        table.innerHTML += `
        <tr>

            <td>${count}</td>

            <td>${profileName}</td>

            <td>${c.email || ""}</td>

            <td class="hidden">${c.phone || ""}</td>

            <td>${c.location || ""}</td>

            <td class="hidden">${c.designation || ""}</td>

            <td>${formatExperience(c.experience || c.total_experience_years) || ""}</td>

            <td class="hidden">${c.last_company || ""}</td>

            <td class="hidden">${c.last_working_date || ""}</td>

            <td class="hidden">${c.matched_skills || ""}</td>

            <td class="hidden">${safeHtml(cleanedCandidateMissingSkills(c).join(", "))}</td>

            <td class="hidden">${c.skill_match_percent || ""}</td>

            <td class="hidden">${c.industry || ""}</td>

            <td class="hidden">${c.domain || ""}</td>

            <td class="hidden">${c.education || ""}</td>

            <td class="hidden">Shortlisted</td>

            <td>${score}</td>

            <td>
                <button onclick="removeShortlist('${c.id}')"
                class="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded text-sm">
                    Remove
                </button>
            </td>

        </tr>
        `
    })

    // * NO RESULT CASE
    if(count === 0){
        table.innerHTML = `
        <tr>
            <td colspan="18" style="text-align:center;padding:20px;color:#6b7280">
                No candidates match this score filter
            </td>
        </tr>
        `
    }
}

function toggleShortlistColumnPanel(){

let panel = document.getElementById("shortlistColumnPanel")

if(!panel) return

if(panel.style.display === "none" || panel.style.display === ""){

panel.style.display = "grid"

}else{

panel.style.display = "none"

}

}



function createJobManagementCard(job, mode, isInactive=false){

let jobId = job.id || job.job_id
let title = safeHtml(job.job_title || "Untitled Job")
let company = safeHtml(job.company_name || "Company not specified")
let location = safeHtml(job.location || "N/A")
let salary = safeHtml(job.salary_range || "Not specified")
let jobType = safeHtml(job.job_type || "N/A")
let description = safeHtml(job.jd_text ? shortText(job.jd_text, 145) : "No description added yet.")
let applicants = job.total_applicants || 0
let topScore = job.top_score || 0
let statusLabel = isInactive ? "Inactive" : "Active"
let cardState = isInactive ? "is-inactive" : "is-active"
let action = ""

if(mode === "edit"){
action = isInactive
? `<button onclick="activateJob('${safeJs(jobId)}')" class="ats-manage-btn ats-manage-btn-activate">Activate Job</button>`
: `<button onclick="openEditJob('${safeJs(jobId)}')" class="ats-manage-btn ats-manage-btn-edit">Edit Job</button>`
}

if(mode === "apply"){
action = isInactive
? `<button disabled class="ats-manage-btn ats-manage-btn-disabled">Inactive</button>`
: `<button onclick="openApplyPage('${safeJs(jobId)}')" class="ats-manage-btn ats-manage-btn-apply">Open Apply Page</button>`
}

if(mode === "delete"){
action = `<button onclick="deleteJob('${safeJs(jobId)}')" class="ats-manage-btn ats-manage-btn-delete">Delete Job</button>`
}

return `

<article class="ats-management-card ${cardState}">
<div class="ats-management-card-top">
<span class="ats-management-icon">JD</span>
<span class="ats-management-status">${statusLabel}</span>
</div>

<div class="ats-management-card-body">
<h3 title="${title}">${title}</h3>
<p>${company}</p>
</div>

<div class="ats-management-meta">
<span><strong>Location</strong>${location}</span>
<span><strong>Salary</strong>${salary}</span>
<span><strong>Type</strong>${jobType}</span>
</div>

<div class="ats-management-desc">${description}</div>

<div class="ats-management-actions">
${action}
</div>

<div class="ats-management-footer">
<span>Applicants <strong>${applicants}</strong></span>
<span>Top Score <strong>${topScore}</strong></span>
</div>
</article>

`
}

function createEditJobCard(job, isInactive=false){
return createJobManagementCard(job, "edit", isInactive)
}
let editActiveExpanded = false
let editInactiveExpanded = false

async function loadEditJobs(){

let res = await fetch(API+"/jobs", {
    headers: authHeaders()
})
let jobs = await res.json()

let active = document.getElementById("activeJobsContainer")
let inactive = document.getElementById("inactiveJobsContainer")

let activeMore = document.getElementById("editActiveViewMore")
let inactiveMore = document.getElementById("editInactiveViewMore")

active.innerHTML=""
inactive.innerHTML=""

let activeJobs = jobs.filter(j=>j.is_active === true)
let inactiveJobs = jobs.filter(j=>j.is_active === false)

/* ACTIVE JOBS */

activeJobs.slice(0,3).forEach(job=>{
active.innerHTML += createEditJobCard(job)
})

if(activeJobs.length > 3){
activeMore.classList.remove("hidden")
}else{
activeMore.classList.add("hidden")
}

/* INACTIVE JOBS */

inactiveJobs.slice(0,3).forEach(job=>{
inactive.innerHTML += createEditJobCard(job,true)
})

if(inactiveJobs.length > 3){
inactiveMore.classList.remove("hidden")
}else{
inactiveMore.classList.add("hidden")
}

/* RESET ARROWS */

document.getElementById("editActiveArrow").innerHTML="More"
document.getElementById("editInactiveArrow").innerHTML="More"

editActiveExpanded = false
editInactiveExpanded = false

}



function toggleEditActiveJobs(){

if(!editActiveExpanded){

openAllEditJobs()

document.getElementById("editActiveArrow").innerHTML="Less"

editActiveExpanded = true

}else{

loadEditJobs()

document.getElementById("editActiveArrow").innerHTML="More"

editActiveExpanded = false

}

}



function toggleEditInactiveJobs(){

if(!editInactiveExpanded){

openAllEditInactiveJobs()

document.getElementById("editInactiveArrow").innerHTML="Less"

editInactiveExpanded = true

}else{

loadEditJobs()

document.getElementById("editInactiveArrow").innerHTML="More"

editInactiveExpanded = false

}

}



function openAllEditJobs(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

let container=document.getElementById("activeJobsContainer")

container.innerHTML=""

jobs
.filter(j=>j.is_active===true)
.forEach(job=>{

container.innerHTML+=createEditJobCard(job)

})

})

}



function openAllEditInactiveJobs(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

let container=document.getElementById("inactiveJobsContainer")

container.innerHTML=""

jobs
.filter(j=>j.is_active===false)
.forEach(job=>{

container.innerHTML+=createEditJobCard(job,true)

})

})

}

function createApplyJobCard(job,isInactive=false){

return createJobManagementCard(job, "apply", isInactive)
}
function openApplyPage(jobId){

window.open(
API + "/apply/" + encodeURIComponent(jobId),
"_blank"
)

}


async function loadApplyJobs(){

let res = await fetch(API+"/jobs", {
    headers: authHeaders()
})
let jobs = await res.json()

let active = document.getElementById("applyActiveJobsContainer")
let inactive = document.getElementById("applyInactiveJobsContainer")

let activeMore = document.getElementById("applyActiveViewMore")
let inactiveMore = document.getElementById("applyInactiveViewMore")

if(!active || !inactive) return

active.innerHTML=""
inactive.innerHTML=""

let activeJobs = jobs.filter(j=>j.is_active === true)
let inactiveJobs = jobs.filter(j=>j.is_active === false)

/* ACTIVE JOBS */

activeJobs.slice(0,3).forEach(job=>{
active.innerHTML += createApplyJobCard(job)
})

/* INACTIVE JOBS */

inactiveJobs.slice(0,3).forEach(job=>{
inactive.innerHTML += createApplyJobCard(job,true)
})

/* ARROW SHOW */

if(activeJobs.length > 3){
activeMore.classList.remove("hidden")
}else{
activeMore.classList.add("hidden")
}

if(inactiveJobs.length > 3){
inactiveMore.classList.remove("hidden")
}else{
inactiveMore.classList.add("hidden")
}

// * RESET ARROWS + STATE
document.getElementById("applyActiveArrow").innerHTML="More"
document.getElementById("applyInactiveArrow").innerHTML="More"

applyActiveExpanded = false
applyInactiveExpanded = false

}



let applyActiveExpanded=false
let applyInactiveExpanded=false

function toggleApplyActiveJobs(){

if(!applyActiveExpanded){

openAllApplyActiveJobs()   // note IMPORTANT (new function)

document.getElementById("applyActiveArrow").innerHTML="Less"

applyActiveExpanded = true

}else{

loadApplyJobs()

document.getElementById("applyActiveArrow").innerHTML="More"

applyActiveExpanded = false

}

}



function toggleApplyInactiveJobs(){

if(!applyInactiveExpanded){

openAllApplyInactiveJobs()   // note IMPORTANT

document.getElementById("applyInactiveArrow").innerHTML="Less"

applyInactiveExpanded = true

}else{

loadApplyJobs()

document.getElementById("applyInactiveArrow").innerHTML="More"

applyInactiveExpanded = false

}

}


/* EXPAND ACTIVE */
function openAllApplyActiveJobs(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

let container = document.getElementById("applyActiveJobsContainer")

container.innerHTML=""

jobs
.filter(j=>j.is_active===true)
.forEach(job=>{
container.innerHTML += createApplyJobCard(job)
})

})

}



/* EXPAND INACTIVE */

function openAllInactiveJobs(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

let container=document.getElementById("applyInactiveJobsContainer")

container.innerHTML=""

jobs
.filter(j=>j.is_active===false)
.forEach(job=>{

container.innerHTML+=createApplyJobCard(job,true)

})

})

}

/* ================= DELETE JOB CARD ================= */
function createDeleteJobCard(job,isInactive=false){

return createJobManagementCard(job, "delete", isInactive)
}


/* ================= LOAD DELETE JOBS ================= */

async function loadDeleteJobs(){

let res = await fetch(API+"/jobs", {
    headers: authHeaders()
})
let jobs = await res.json()

let active = document.getElementById("deleteActiveJobsContainer")
let inactive = document.getElementById("deleteInactiveJobsContainer")

let activeMore = document.getElementById("deleteActiveViewMore")
let inactiveMore = document.getElementById("deleteInactiveViewMore")

if(!active || !inactive) return

active.innerHTML=""
inactive.innerHTML=""

let activeJobs = jobs.filter(j=>j.is_active === true)
let inactiveJobs = jobs.filter(j=>j.is_active === false)

/* ACTIVE */

activeJobs.slice(0,3).forEach(job=>{
active.innerHTML += createDeleteJobCard(job)
})

/* INACTIVE */

inactiveJobs.slice(0,3).forEach(job=>{
inactive.innerHTML += createDeleteJobCard(job,true)
})

/* ARROW SHOW */

if(activeJobs.length > 3){
activeMore.classList.remove("hidden")
}else{
activeMore.classList.add("hidden")
}

if(inactiveJobs.length > 3){
inactiveMore.classList.remove("hidden")
}else{
inactiveMore.classList.add("hidden")
}

}



/* ================= EXPAND STATE ================= */

let deleteActiveExpanded=false
let deleteInactiveExpanded=false



/* ================= TOGGLE ACTIVE ================= */

function toggleDeleteActiveJobs(){

if(!deleteActiveExpanded){

openAllDeleteActiveJobs()

document.getElementById("deleteActiveArrow").innerHTML="Less"

deleteActiveExpanded = true

}else{

loadDeleteJobs()

document.getElementById("deleteActiveArrow").innerHTML="More"

deleteActiveExpanded = false

}

}



/* ================= TOGGLE INACTIVE ================= */

function toggleDeleteInactiveJobs(){

if(!deleteInactiveExpanded){

openAllDeleteInactiveJobs()

document.getElementById("deleteInactiveArrow").innerHTML="Less"

deleteInactiveExpanded = true

}else{

loadDeleteJobs()

document.getElementById("deleteInactiveArrow").innerHTML="More"

deleteInactiveExpanded = false

}

}



/* ================= EXPAND ACTIVE ================= */

function openAllDeleteActiveJobs(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

let container=document.getElementById("deleteActiveJobsContainer")

container.innerHTML=""

jobs
.filter(j=>j.is_active===true)
.forEach(job=>{

container.innerHTML+=createDeleteJobCard(job)

})

})

}



/* ================= EXPAND INACTIVE ================= */

function openAllDeleteInactiveJobs(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

let container=document.getElementById("deleteInactiveJobsContainer")

container.innerHTML=""

jobs
.filter(j=>j.is_active===false)
.forEach(job=>{

container.innerHTML+=createDeleteJobCard(job,true)

})

})

}



/* ================= DELETE JOB ================= */

async function deleteJob(id){

if(!confirm("Are you sure you want to delete this job?")) return

try{

let res = await fetch(API + "/jobs/" + id,{
method:"DELETE"
})

let data = await res.json()


alert("Job Deleted Successfully")

loadDeleteJobs()

}catch(err){


alert("Delete failed")

}

}


async function openEditJob(jobId){


// page open
showPage("editForm")

// fetch job
let res = await fetch(API + "/public-job/" + jobId)

let job = await res.json()

// fill form
document.getElementById("editJobId").value = job.job_id || job.id
document.getElementById("editJobTitle").value = job.job_title || ""
document.getElementById("editCompany").value = job.company_name || ""
document.getElementById("editLocation").value = job.location || ""
document.getElementById("editSalary").value = job.salary_range || ""
document.getElementById("editJobType").value = job.job_type || ""
document.getElementById("editJD").value = job.jd_text || ""

}


async function updateJob(){

let jobId = document.getElementById("editJobId").value

let data = {

job_title: document.getElementById("editJobTitle").value,
company_name: document.getElementById("editCompany").value,
department: document.getElementById("editDepartment").value,
location: document.getElementById("editLocation").value,
work_mode: document.getElementById("editWorkMode").value,
job_type: document.getElementById("editJobType").value,
experience_required: document.getElementById("editExperience").value,
salary_range: document.getElementById("editSalary").value,
hiring_manager: document.getElementById("editHiringManager").value,
application_deadline: document.getElementById("editDeadline").value,
jd_text: document.getElementById("editJD").value

}

await fetch(API+"/edit-job/"+jobId,{
method:"PUT",
headers:{"Content-Type":"application/json"},
body:JSON.stringify(data)
})

alert("Job Updated Successfully")

loadEditJobs()

}


async function activateJob(jobId){

if(!confirm("Activate this job?")) return

await fetch(API+"/activate-job/"+jobId,{
method:"PUT"
})

alert("Job Activated")

loadEditJobs()
loadApplyJobs()
loadDashboard(true)

}

let recruiterExpanded = false

function toggleRecruiterJobs(){

if(!recruiterExpanded){

openAllActiveJobs()

recruiterExpanded = true

}else{

loadJobs()

recruiterExpanded = false

}

}

function openAllActiveJobs(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

let container = document.getElementById("jobCards")

container.innerHTML=""

jobs
.filter(j => j.is_active === true)   // * ONLY ACTIVE
.forEach(job=>{

container.innerHTML += `

<div class="job-card">

<div>

<div class="job-title">
${job.job_title}
</div>

<div class="company-name">
${job.company_name}
</div>

<div class="job-info">

<div><span>Location:</span> ${job.location || "N/A"}</div>

<div><span>Salary:</span> ${job.salary_range || "Not specified"}</div>

<div><span>Job Type:</span> ${job.job_type || "N/A"}</div>

</div>

<div class="job-desc">

<strong>Job Description:</strong><br>

${job.jd_text ? job.jd_text.substring(0,120) + "..." : "No description"}

</div>

</div>

<button
class="result-btn"
onclick="openJobResult('${job.id}','${job.job_title}')">

View Results

</button>

<div class="job-footer">

<span>Applicants: ${job.total_applicants || 0}</span>

<span>Top Score: ${job.top_score || 0}</span>

</div>

</div>

`

})

})

}

function openAllActiveJobsModern(){

fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{
updateRecruiterSummary(jobs)

let container = document.getElementById("jobCards")
if(!container) return

container.innerHTML=""

jobs
.filter(j => j.is_active === true)
.forEach(job=>{
container.innerHTML += createRecruiterJobCard(job)
})

})

}

openAllActiveJobs = openAllActiveJobsModern

function openShortlistExplanation(){

let rows = shortlistExportRows()

if(!rows.length){
alert("No shortlisted candidates available for AI explanation. Select a job and load shortlisted candidates first.")
return
}

showPage("shortlistExplanation")
renderShortlistExplanationLoading(rows)
generateShortlistExplanation(rows)

}

function renderShortlistExplanationLoading(rows){
let totalEl = document.getElementById("shortlistExplainTotal")
let statusEl = document.getElementById("shortlistExplainStatus")
let bodyEl = document.getElementById("shortlistExplainBody")
let jobEl = document.getElementById("shortlistExplainJob")

if(totalEl) totalEl.innerText = `${rows.length} candidates`
if(statusEl) statusEl.innerText = "Sending shortlist table + JD to AI model"
if(jobEl){
let select = document.getElementById("shortlistJobSelect")
jobEl.innerText = select?.selectedOptions?.[0]?.textContent?.trim() || "Selected job"
}
if(bodyEl){
bodyEl.innerHTML = `
<div class="ats-shortlist-explain-loading">
<span></span>
<h3>Generating AI Explanation</h3>
<p>Analyzing the complete shortlisted table, hidden columns, scores, skill evidence, and selected JD context.</p>
</div>
`
}
}

async function selectedShortlistJobPayload(){
let jobSelect = document.getElementById("shortlistJobSelect")
let jobId = jobSelect ? jobSelect.value : ""
let selectedText = jobSelect?.selectedOptions?.[0]?.textContent?.trim() || ""
let fallback = {id: jobId, job_title: selectedText}

if(!jobId) return fallback

try{
let res = await fetch(API + "/jobs", {headers: authHeaders()})
let jobs = await res.json()
let job = Array.isArray(jobs) ? jobs.find(item => String(item.id) === String(jobId)) : null
return job || fallback
}catch(err){
return fallback
}
}

function localShortlistExplanation(rows, job){
let total = rows.length
let avgScore = total ? (rows.reduce((sum,row)=>sum + (Number(row.score) || 0), 0) / total).toFixed(1) : "0.0"
let top = [...rows].sort((a,b)=>(Number(b.score) || 0) - (Number(a.score) || 0))[0] || {}
let skillCounts = {}
rows.forEach(row=>{
normalizeList(row.matched_skills).forEach(skill=>{
skillCounts[skill] = (skillCounts[skill] || 0) + 1
})
})
let topSkills = topEntries(skillCounts, 5)

return {
generated:false,
headline:`${total} shortlisted candidates for recruiter review`,
executive_summary:`The shortlist for ${job?.job_title || "the selected role"} contains ${total} candidates with an average score of ${avgScore}. ${top.name || "The top candidate"} is currently the strongest score-based profile at ${formatScore(top.score)}. The list should be reviewed against JD-critical skills, experience depth, education, and missing evidence before outreach. Hidden table columns were included in this assessment where available. Use this explanation as a recruiter review layer, not an automatic hiring decision.`,
shortlist_quality:`This shortlist has a score range from ${formatScore(Math.min(...rows.map(row=>Number(row.score) || 0)))} to ${formatScore(Math.max(...rows.map(row=>Number(row.score) || 0)))}. Candidates with stronger scores should be reviewed first, while lower-score shortlisted profiles need skill-gap validation.`,
candidate_priorities:[
`Review ${top.name || "the highest-scoring candidate"} first because this profile has the strongest stored score.`,
`Compare candidates with similar scores using location, experience, matched skills, and missing skills.`,
"Check rows with blank hidden-column values before moving them to communication."
],
skill_observations:topSkills.length ? topSkills.map(([skill,count])=>`${skill} appears in ${count} shortlisted candidate(s).`) : ["Matched skill evidence is limited in the current table payload."],
risks:["Some hidden fields may be blank, so verify full resume evidence before outreach.","AI score and shortlist status should be validated against mandatory JD requirements."],
next_steps:["Review highest-scoring candidates first.","Validate JD-critical missing skills in screening.","Move recruiter-approved candidates to communication."]
}
}

async function generateShortlistExplanation(rows){
let statusEl = document.getElementById("shortlistExplainStatus")
let job = await selectedShortlistJobPayload()
let payload = {
job_id: job?.id || document.getElementById("shortlistJobSelect")?.value || "",
job,
candidates: rows
}

try{
let res = await fetch(API + "/ai-shortlist-explanation", {
method:"POST",
headers: authHeaders(),
body: JSON.stringify(payload)
})
if(!res.ok) throw new Error("AI shortlist explanation endpoint unavailable")
let data = await res.json()
if(!data || !data.headline || !data.executive_summary){
throw new Error("AI shortlist explanation response was incomplete")
}
currentShortlistExplanation = data
if(statusEl) statusEl.innerText = data.generated ? "OpenAI generated explanation" : "Stored-data fallback explanation"
renderShortlistExplanation(data, rows, job)
}catch(err){
let fallback = localShortlistExplanation(rows, job)
currentShortlistExplanation = fallback
if(statusEl) statusEl.innerText = "Fallback explanation generated from table data"
renderShortlistExplanation(fallback, rows, job)
}
}

function renderExplanationList(items, className=""){
let clean = Array.isArray(items) ? items.filter(item => safeText(item).trim()) : []
return clean.length ? clean.map(item=>`<li class="${safeHtml(className)}">${safeHtml(item)}</li>`).join("") : `<li>No signal available.</li>`
}

function renderShortlistExplanation(explanation, rows, job){
let bodyEl = document.getElementById("shortlistExplainBody")
let totalEl = document.getElementById("shortlistExplainTotal")
let headlineEl = document.getElementById("shortlistExplainHeadline")
let jobEl = document.getElementById("shortlistExplainJob")

if(totalEl) totalEl.innerText = `${rows.length} candidates`
if(headlineEl) headlineEl.innerText = explanation.headline || "Shortlist AI Explanation"
if(jobEl) jobEl.innerText = job?.job_title || "Selected job"
if(!bodyEl) return

let sortedRows = [...rows].sort((a,b)=>(Number(b.score) || 0) - (Number(a.score) || 0)).slice(0,6)

bodyEl.innerHTML = `
<section class="ats-shortlist-explain-grid">
<article class="ats-shortlist-explain-main">
<div class="ats-shortlist-explain-card-head">
<span>${safeHtml(explanation.generated ? "AI model output" : "Fallback output")}</span>
<h3>Executive Summary</h3>
</div>
<p>${safeHtml(explanation.executive_summary || "No explanation generated.")}</p>
</article>

<article class="ats-shortlist-explain-main is-quality">
<div class="ats-shortlist-explain-card-head">
<span>JD alignment</span>
<h3>Shortlist Quality</h3>
</div>
<p>${safeHtml(explanation.shortlist_quality || "Review shortlist quality against the JD.")}</p>
</article>
</section>

<section class="ats-shortlist-explain-lists">
<article>
<h3>Candidate Priorities</h3>
<ul>${renderExplanationList(explanation.candidate_priorities, "is-priority")}</ul>
</article>
<article>
<h3>Skill Observations</h3>
<ul>${renderExplanationList(explanation.skill_observations, "is-skill")}</ul>
</article>
<article>
<h3>Risks To Validate</h3>
<ul>${renderExplanationList(explanation.risks, "is-risk")}</ul>
</article>
<article>
<h3>Next Steps</h3>
<ul>${renderExplanationList(explanation.next_steps, "is-next")}</ul>
</article>
</section>

<section class="ats-shortlist-explain-table">
<div class="ats-shortlist-explain-card-head">
<span>Table payload sent</span>
<h3>Candidate Evidence Used</h3>
</div>
<div>
${sortedRows.map((row,index)=>`
<article>
<b>#${index + 1}</b>
<div>
<strong>${safeHtml(row.name || "Candidate")}</strong>
<small>${safeHtml(row.email || "No email")} | ${safeHtml(row.location || "Location not listed")} | ${safeHtml(row.experience || "Experience not listed")}</small>
</div>
<span>${safeHtml(formatScore(row.score))}</span>
</article>
`).join("")}
</div>
</section>
`
}

function openShortlistAnalytics(){

if(!currentShortlistResults.length){
let rows = Array.from(document.querySelectorAll("#shortlistTable tr.ats-shortlist-row"))
currentShortlistResults = rows.map(row => {
let cells = row.children
return {
name: cells[1]?.innerText?.split("\n")[1] || cells[1]?.innerText || "Candidate",
email: cells[2]?.innerText || "",
location: cells[4]?.innerText || "",
experience: cells[6]?.innerText || "",
score: Number(cells[16]?.innerText || 0),
status: cells[15]?.innerText || "Shortlisted",
matched_skills: cells[9]?.innerText || "",
missing_skills: cells[10]?.innerText || "",
education: cells[14]?.innerText || ""
}
}).filter(candidate => safeText(candidate.name).trim())
}

if(!currentShortlistResults.length){
alert("No shortlisted candidates available for analytics. Select a job and load shortlisted candidates first.")
return
}

showPage("shortlistAnalytics")
renderShortlistAnalytics(currentShortlistResults)

}

function shortlistExportRows(){
let source = currentShortlistResults.length ? currentShortlistResults : []

if(!source.length){
let rows = Array.from(document.querySelectorAll("#shortlistTable tr.ats-shortlist-row"))
source = rows.map((row, index) => {
let cells = row.children
return {
rank: index + 1,
name: cells[1]?.querySelector(".ats-shortlist-name-link")?.innerText || cells[1]?.innerText || "",
email: cells[2]?.innerText || "",
phone: cells[3]?.innerText || "",
location: cells[4]?.innerText || "",
designation: cells[5]?.innerText || "",
experience: cells[6]?.innerText || "",
last_company_name: cells[7]?.innerText || "",
last_working_date: cells[8]?.innerText || "",
matched_skills: cells[9]?.innerText || "",
missing_skills: cells[10]?.innerText || "",
skill_match_percent: cells[11]?.innerText || "",
industry: cells[12]?.innerText || "",
domain: cells[13]?.innerText || "",
education: cells[14]?.innerText || "",
status: cells[15]?.innerText || "",
score: cells[16]?.innerText || ""
}
})
}

return source.map((candidate, index) => {
let model = shortlistCandidateModel(candidate)
return {
rank: index + 1,
name: model.full_name || candidate.name || candidate.full_name || "",
email: model.email || "",
phone: model.phone || "",
location: model.location || "",
designation: model.designation || "",
experience: formatExperience(model.total_experience_years ?? candidate.experience),
last_company: model.last_company_name || candidate.last_company || "",
last_working_date: candidate.last_working_date || "",
matched_skills: textList(cleanedCandidateMatchedSkills(model), ""),
missing_skills: textList(cleanedCandidateMissingSkills(model), ""),
skill_match_percent: candidate.skill_match_percent || model.skill_match_percent || "",
industry: model.industry || "",
domain: model.domain || "",
education: model.education || "",
status: model.status || "Shortlisted",
score: formatScore(model.final_score ?? candidate.score)
}
})
}

function csvEscape(value){
let text = safeText(value).replace(/\r?\n|\r/g, " ").trim()
return `"${text.replace(/"/g, '""')}"`
}

function downloadCsvFile(filename, rows){
let csv = rows.map(row => row.map(csvEscape).join(",")).join("\r\n")
let blob = new Blob(["\ufeff" + csv], {type:"text/csv;charset=utf-8;"})
let url = URL.createObjectURL(blob)
let link = document.createElement("a")
link.href = url
link.download = filename
document.body.appendChild(link)
link.click()
document.body.removeChild(link)
setTimeout(()=>URL.revokeObjectURL(url), 1000)
}

function filenameFromContentDisposition(value){
let text = safeText(value)
let utfMatch = text.match(/filename\*=UTF-8''([^;]+)/i)
if(utfMatch) return decodeURIComponent(utfMatch[1])
let match = text.match(/filename="?([^";]+)"?/i)
return match ? match[1] : ""
}

async function openResumeDownload(resumeId){
if(!resumeId){
alert("Candidate resume id is missing.")
return
}
try{
let res = await fetch(API + "/download-resume/" + encodeURIComponent(resumeId), {
headers: {
"Authorization": "Bearer " + localStorage.getItem("token")
}
})

if(!res.ok){
let message = "Could not download resume."
try{
let data = await res.json()
message = data.detail || data.error || message
}catch(err){}
alert(message)
return
}

let blob = await res.blob()
let filename = filenameFromContentDisposition(res.headers.get("content-disposition")) || "resume"
let url = URL.createObjectURL(blob)
let link = document.createElement("a")
link.href = url
link.download = filename
document.body.appendChild(link)
link.click()
document.body.removeChild(link)
setTimeout(()=>URL.revokeObjectURL(url), 1000)
}catch(error){
alert("Could not download resume. Please try again.")
}
}

function downloadShortlisted(){
let rows = shortlistExportRows()

if(!rows.length){
alert("No shortlisted candidates available to download. Select a job and load shortlisted candidates first.")
return
}

let headers = [
"Rank",
"Name",
"Email",
"Phone",
"Location",
"Designation",
"Experience",
"Last Company",
"Last Working Date",
"Matched Skills",
"Missing Skills",
"Skill Match %",
"Industry",
"Domain",
"Education",
"Status",
"Score"
]

let csvRows = [
headers,
...rows.map(row => [
row.rank,
row.name,
row.email,
row.phone,
row.location,
row.designation,
row.experience,
row.last_company,
row.last_working_date,
row.matched_skills,
row.missing_skills,
row.skill_match_percent,
row.industry,
row.domain,
row.education,
row.status,
row.score
])
]

let jobSelect = document.getElementById("shortlistJobSelect")
let jobName = jobSelect?.selectedOptions?.[0]?.textContent || "shortlisted-candidates"
let cleanJobName = safeText(jobName).replace(/[^\w\s-]/g, "").replace(/\s+/g, "-").slice(0,60) || "shortlisted-candidates"
let date = new Date().toISOString().slice(0,10)
downloadCsvFile(`${cleanJobName}-${date}.csv`, csvRows)
}

function openClientShortlistReport(){
let jobSelect = document.getElementById("shortlistJobSelect")
let jobId = jobSelect ? jobSelect.value : window.currentJobId
if(!jobId){
alert("Select a job first.")
return
}
window.open(API + "/client-shortlist-report/" + encodeURIComponent(jobId), "_blank")
}

function numberFromText(value){
let match = safeText(value).match(/[\d.]+/)
return match ? Number(match[0]) || 0 : 0
}

function bucketLabel(value, buckets){
for(let bucket of buckets){
if(value >= bucket.min && value < bucket.max) return bucket.label
}
return buckets[buckets.length - 1]?.label || "Other"
}

function countBy(items, getter){
let map = {}
items.forEach(item=>{
let key = safeText(getter(item)).trim() || "Not listed"
map[key] = (map[key] || 0) + 1
})
return map
}

function topEntries(map, limit=8){
return Object.entries(map || {}).sort((a,b)=>b[1]-a[1]).slice(0,limit)
}

function shortlistCandidateModel(candidate){
let score = Number(candidate.score ?? candidate.final_score ?? 0) || 0
let experience = Number(candidate.total_experience_years ?? candidate.experience_years ?? candidate.experience ?? numberFromText(candidate.experience)) || 0
let name = candidate.name || candidate.full_name || "Candidate"
return normalizeCandidateForProfile({
...candidate,
name,
full_name: name,
score,
final_score: score,
experience,
total_experience_years: experience,
key_skills: candidate.key_skills || candidate.skills || candidate.matched_skills,
status: candidate.status || "Shortlisted"
})
}

function destroyShortlistAnalyticsCharts(){
Object.values(shortlistAnalyticsCharts).forEach(chart => {
if(chart && typeof chart.destroy === "function") chart.destroy()
})
shortlistAnalyticsCharts = {}
}

function renderShortlistMetric(id, value, label){
let el = document.getElementById(id)
if(!el) return
el.innerHTML = `<strong>${safeHtml(value)}</strong><span>${safeHtml(label)}</span>`
}

function renderShortlistAnalytics(candidates){
let normalized = (candidates || []).map(shortlistCandidateModel)
let total = normalized.length
let scores = normalized.map(c=>Number(c.final_score) || 0)
let avgScore = total ? (scores.reduce((sum, score)=>sum + score, 0) / total).toFixed(1) : "0.0"
let topCandidate = [...normalized].sort(compareCandidateRank)[0] || {}
let avgExp = total ? (normalized.reduce((sum, c)=>sum + (Number(c.total_experience_years) || 0), 0) / total).toFixed(1) : "0.0"
let strongCount = normalized.filter(c => (Number(c.final_score) || 0) >= 60).length

renderShortlistMetric("shortlistAnalyticsTotal", total, "shortlisted candidates")
renderShortlistMetric("shortlistAnalyticsAvg", avgScore, "average AI score")
renderShortlistMetric("shortlistAnalyticsTop", topCandidate.full_name || "N/A", `top score ${formatScore(candidateRecruiterScore(topCandidate))}`)
renderShortlistMetric("shortlistAnalyticsExp", avgExp, "average years")

let jobLabel = document.getElementById("shortlistAnalyticsJob")
let jobSelect = document.getElementById("shortlistJobSelect")
if(jobLabel){
let selectedJob = jobSelect?.selectedOptions?.[0]?.textContent?.trim() || "Selected shortlist"
jobLabel.innerText = selectedJob
}

let scoreBuckets = {"0-39":0,"40-59":0,"60-79":0,"80-100":0}
scores.forEach(score=>{
if(score < 40) scoreBuckets["0-39"]++
else if(score < 60) scoreBuckets["40-59"]++
else if(score < 80) scoreBuckets["60-79"]++
else scoreBuckets["80-100"]++
})

let expBuckets = {"0-1":0,"1-3":0,"3-5":0,"5+":0}
normalized.forEach(c=>{
let exp = Number(c.total_experience_years) || 0
if(exp < 1) expBuckets["0-1"]++
else if(exp < 3) expBuckets["1-3"]++
else if(exp < 5) expBuckets["3-5"]++
else expBuckets["5+"]++
})

let skillCounts = {}
normalized.forEach(candidate=>{
cleanedCandidateMatchedSkills(candidate).forEach(skill=>{
skillCounts[skill] = (skillCounts[skill] || 0) + 1
})
})
let topSkills = topEntries(skillCounts, 8)
let locations = topEntries(countBy(normalized, c=>c.location), 6)

let skillList = document.getElementById("shortlistAnalyticsSkills")
if(skillList){
skillList.innerHTML = topSkills.length ? topSkills.map(([skill, count])=>{
let percent = total ? Math.round((count / total) * 100) : 0
return `
<article class="ats-shortlist-skill-row">
<div><strong>${safeHtml(skill)}</strong><span>${safeHtml(count)} candidates</span></div>
<div class="ats-shortlist-meter" style="--meter:${percent}%"><span></span></div>
</article>
`
}).join("") : `<div class="ats-empty-state">No skill evidence available.</div>`
}

let candidateList = document.getElementById("shortlistAnalyticsCandidates")
if(candidateList){
candidateList.innerHTML = normalized
.sort(compareCandidateRank)
.slice(0,8)
.map((candidate,index)=>`
<article class="ats-shortlist-analytics-candidate">
<span>#${index + 1}</span>
<div>
<strong>${safeHtml(candidate.full_name)}</strong>
<small>${safeHtml(candidate.location || "Location not listed")} | ${safeHtml(formatExperience(candidate.total_experience_years))}</small>
</div>
<b>${safeHtml(formatScore(candidateRecruiterScore(candidate)))}</b>
</article>
`).join("")
}

let insights = document.getElementById("shortlistAnalyticsInsights")
if(insights){
let bestSkill = topSkills[0]?.[0] || "core JD skills"
let bestLocation = locations[0]?.[0] || "mixed locations"
let strongShare = total ? Math.round((strongCount / total) * 100) : 0
insights.innerHTML = `
<li>${safeHtml(strongShare)}% of shortlisted candidates are above the strong-review score threshold.</li>
<li>${safeHtml(bestSkill)} is the strongest repeated evidence in this shortlist.</li>
<li>${safeHtml(bestLocation)} has the highest candidate concentration.</li>
<li>Prioritize top-score profiles first, then validate missing JD evidence during screening.</li>
`
}

destroyShortlistAnalyticsCharts()
if(typeof Chart !== "undefined"){
let scoreCanvas = document.getElementById("shortlistScoreChart")
let expCanvas = document.getElementById("shortlistExperienceChart")
let locationCanvas = document.getElementById("shortlistLocationChart")

if(scoreCanvas){
shortlistAnalyticsCharts.score = new Chart(scoreCanvas, {
type:"bar",
data:{labels:Object.keys(scoreBuckets), datasets:[{label:"Candidates", data:Object.values(scoreBuckets), backgroundColor:["#f43f5e","#f59e0b","#2563eb","#10b981"], borderRadius:10}]},
options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true, ticks:{precision:0}}}}
})
}

if(expCanvas){
shortlistAnalyticsCharts.experience = new Chart(expCanvas, {
type:"doughnut",
data:{labels:Object.keys(expBuckets), datasets:[{data:Object.values(expBuckets), backgroundColor:["#6366f1","#22c55e","#f59e0b","#ef4444"], borderWidth:0}]},
options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{position:"bottom"}}}
})
}

if(locationCanvas){
shortlistAnalyticsCharts.location = new Chart(locationCanvas, {
type:"bar",
data:{labels:locations.map(([label])=>shortText(label, 20)), datasets:[{label:"Candidates", data:locations.map(([,count])=>count), backgroundColor:"#14b8a6", borderRadius:10}]},
options:{indexAxis:"y", responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{beginAtZero:true, ticks:{precision:0}}}}
})
}
}
}

async function loadShortlistJobDropdown(){

let res = await fetch(API + "/jobs", {
    headers: {
        "Authorization": "Bearer " + localStorage.getItem("token")
    }
})
let jobs = await res.json()

let select = document.getElementById("shortlistJobSelect")

if(!select) return

let selectedValue = select.value

select.innerHTML = `<option value="">SELECT JOBS</option>`

jobs
.filter(job => job.is_active === true)
.forEach(job => {

select.innerHTML += `
<option value="${safeHtml(job.id)}" title="${safeHtml(job.job_title)}">
${safeHtml(shortText(job.job_title, 70))}
</option>
`

})

if(selectedValue){
select.value = selectedValue
}

}

function toggleApply(jobId){

let all = document.querySelectorAll('[id^="apply-"]')

// sab band karo
all.forEach(el=>{
if(el.id !== "apply-"+jobId){
el.style.display = "none"
}
})

// current toggle
let current = document.getElementById("apply-"+jobId)

if(!current) return

if(current.style.display === "block"){
current.style.display = "none"
}else{
current.style.display = "block"
}

}
function openApplySection(jobId){

let container = document.getElementById("applyActiveJobsContainer")

// sab jobs reload karo
fetch(API+"/jobs")
.then(res=>res.json())
.then(jobs=>{

container.innerHTML=""

// sirf active jobs
jobs
.filter(j=>j.is_active===true)
.forEach(job=>{

let isOpen = (job.id == jobId || job.job_id == jobId)

container.innerHTML += `

<div class="bg-white rounded-2xl shadow p-6">

<h3 class="text-xl font-bold mb-2">${job.job_title}</h3>

<button onclick="openApplySection('${job.id || job.job_id}')"
class="w-full bg-gradient-to-r from-indigo-500 to-purple-600 text-white py-2 rounded mb-3">
Apply Job
</button>

${
isOpen ? `
<div class="p-4 border rounded-lg bg-green-100">
* APPLY OPEN (same like edit page)
</div>
` : ""
}

</div>

`

})

})

}

function sourcingButton(label, value, actionLabel){
return `
<div class="ats-sourcing-copy-row">
<div>
<strong>${safeHtml(label)}</strong>
<input value="${safeHtml(value || "")}" readonly>
</div>
<button type="button" onclick="copySourcingText('${safeJs(actionLabel)}')">Copy</button>
</div>
`
}

function sourcingTextBlock(label, key, value){
return `
<div class="ats-sourcing-post-block">
<div class="ats-sourcing-post-head">
<strong>${safeHtml(label)}</strong>
<button type="button" onclick="copySourcingText('${safeJs(key)}')">Copy</button>
</div>
<textarea readonly>${safeHtml(value || "")}</textarea>
</div>
`
}

function showSuccessModal(data){

let jobId = data?.job_id || data
let links = data?.apply_links || {}
let posts = data?.generated_posts || {}
let mainLink = links.main || data?.apply_link || ("http://127.0.0.1:5500/apply.html?job_id=" + jobId)
latestSourcingData = {
main: mainLink,
linkedin: links.linkedin || "",
whatsapp: links.whatsapp || "",
naukri: links.naukri || "",
referral: links.referral || "",
website: links.website || "",
linkedinPost: posts.linkedin || "",
whatsappMessage: posts.whatsapp || "",
naukriText: posts.naukri || ""
}

document.getElementById("successJobId").innerText = jobId

let panel = document.getElementById("sourcingSuccessPanel")
if(panel){
panel.innerHTML = `
<div class="ats-sourcing-link-list">
${sourcingButton("Main Apply Link", latestSourcingData.main, "main")}
${sourcingButton("LinkedIn Tracking Link", latestSourcingData.linkedin, "linkedin")}
${sourcingButton("WhatsApp Tracking Link", latestSourcingData.whatsapp, "whatsapp")}
${sourcingButton("Naukri Tracking Link", latestSourcingData.naukri, "naukri")}
${sourcingButton("Referral Tracking Link", latestSourcingData.referral, "referral")}
${sourcingButton("Website Tracking Link", latestSourcingData.website, "website")}
</div>
${sourcingTextBlock("LinkedIn Post", "linkedinPost", latestSourcingData.linkedinPost)}
${sourcingTextBlock("WhatsApp Message", "whatsappMessage", latestSourcingData.whatsappMessage)}
${sourcingTextBlock("Naukri Apply Text", "naukriText", latestSourcingData.naukriText)}
<div class="ats-sourcing-actions">
<button type="button" onclick="openSuccessPage()">Preview Apply Page</button>
<span id="sourcingCopyFeedback" aria-live="polite"></span>
</div>
`
}

document.getElementById("jobSuccessModal").classList.remove("hidden")

// note FORM HIDE (IMPORTANT)
document.getElementById("jobPage").classList.add("hidden")

}

async function copyTextValue(value){
try{
if(navigator.clipboard && navigator.clipboard.writeText){
await navigator.clipboard.writeText(value)
return true
}
let temp = document.createElement("textarea")
temp.value = value
temp.setAttribute("readonly", "")
temp.style.position = "fixed"
temp.style.left = "-9999px"
document.body.appendChild(temp)
temp.select()
let ok = document.execCommand("copy")
document.body.removeChild(temp)
return ok
}catch(error){
return false
}
}

async function copySourcingText(key){
let value = latestSourcingData?.[key] || ""
let feedback = document.getElementById("sourcingCopyFeedback")
let ok = value ? await copyTextValue(value) : false
if(feedback){
feedback.textContent = ok ? "Copied" : "Failed to copy"
setTimeout(()=>{ feedback.textContent = "" }, 1800)
}else{
alert(ok ? "Copied" : "Failed to copy")
}
}

function copySuccessLink(){
copySourcingText("main")
}

function openSuccessPage(){
let link = latestSourcingData?.main || ""
if(!link) return
window.open(link, "_blank")
}

function closeSuccessModal(){
document.getElementById("jobSuccessModal").classList.add("hidden")

// note back to dashboard
showPage("dashboard")
}

async function applyShortlistFilter(){

let jobId = document.getElementById("shortlistJobSelect").value
let minScoreValue = document.getElementById("shortlistMinScore").value

if(!minScoreValue){
    refreshRecruiterWorkflow(document.getElementById("shortlistJobSelect")?.value)
    return
}

let minScore = Number(minScoreValue)

if(!Number.isFinite(minScore)){
    alert("Enter a valid score")
    return
}


// OK JSON send karna hai
let res = await fetch(API + "/shortlist-by-filter", {
    method: "POST",
    headers: {
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        job_id: jobId,
        min_score: Number(minScore)
    })
})

let data = await res.json()

if(!res.ok || data.error){
    alert("Could not apply shortlist filter")
    return
}


// * reload
await refreshRecruiterWorkflow(jobId)
}

async function removeShortlist(id){

    let res = await fetch(API + "/shortlist/" + id, {
        method: "DELETE"
    })

    let data = await res.json()

    if(data.error){
        alert("Error: " + data.error)
        return
    }

    alert("OK Removed")

    // * REFRESH TABLE
    refreshRecruiterWorkflow(document.getElementById("shortlistJobSelect")?.value)
}


async function loadCommunicationJobsLegacy(){

let res = await fetch(API + "/jobs", {
    headers: {
        "Authorization": "Bearer " + localStorage.getItem("token")
    }
})
let jobs = await res.json()

let container = document.getElementById("communicationJobsContainer")

if(!container) return

container.innerHTML = ""

jobs
.filter(j => j.is_active === true)
.forEach(job => {

container.innerHTML += `

<div class="bg-white rounded-2xl shadow p-6">

<!-- TITLE -->
<h3 class="text-xl font-bold mb-1">
${job.job_title}
</h3>

<p class="text-indigo-600 mb-3">
${job.company_name}
</p>

<!-- INFO -->
<p class="text-gray-600 text-sm">
<b>Location:</b> ${job.location || "N/A"}
</p>

<p class="text-gray-600 text-sm">
<b>Salary:</b> ${job.salary_range || "Not specified"}
</p>

<p class="text-gray-600 text-sm mb-3">
<b>Job Type:</b> ${job.job_type || "Full Time"}
</p>

<!-- DESCRIPTION -->
<p class="text-gray-500 text-sm mb-6">
<b>Job Description:</b><br>
${job.jd_text ? job.jd_text.substring(0,120)+"..." : "No description"}
</p>

<!-- BUTTON -->
<button 
onclick="openCommunicationPage('${job.id}', '${job.job_title}')"
class="w-full bg-gradient-to-r from-indigo-500 to-purple-600 text-white py-3 rounded-lg font-medium">

View Candidates

</button>

<!-- FOOTER -->
<div class="flex justify-between text-gray-500 text-sm mt-4">

<span>Applicants: ${job.total_applicants || 0}</span>

<span>Top Score: ${job.top_score || 0}</span>

</div>

<!-- CANDIDATES CONTAINER -->
<div id="comm-${job.id}" class="mt-4"></div>

</div>

`

})
}

function getDisplayStatus(c){

  // target STAGE FIRST

  if(c.stage === "communication")
      return "Communication";

  if(c.stage === "shortlisted")
      return "Shortlisted";

  if(c.stage === "rejected")
      return "Rejected";

  if(c.stage === "applied")
      return "Applied";

  // * fallback from backend status

  if(c.status)
      return c.status;

  return "Applied";
}

function getStatusClass(status){
  let normalized = safeText(status).toLowerCase().replace(/\s+/g, "_")
  if(normalized.includes("communication")) return "is-communication"
  if(normalized.includes("shortlist")) return "is-shortlisted"
  if(normalized.includes("reject")) return "is-rejected"
  if(normalized.includes("review")) return "is-review"
  if(normalized.includes("applied")) return "is-applied"
  return "is-neutral"
}

function openCommunicationPage(jobId, jobTitle){

    showPage("communicationResults")

    window.currentJobTitle = jobTitle
    window.currentJobId = jobId
    localStorage.setItem("lastCommunicationJobId", jobId || "")
    localStorage.setItem("lastCommunicationJobTitle", jobTitle || "")

    let title = document.getElementById("communicationResultsTitle")

    if(title){
        title.innerText = jobTitle + " - Communication"
    }

    // * OLD REMOVE
    // loadCommunicationTable(jobId)

    // * NEW ADD
    loadCommunicationSplit(jobId)
}
async function sendMail(email, name, jobTitle, jobId){
    let button = typeof event !== "undefined" ? event.target : null
    let senderPayload = getActiveSenderPayload()
    if(senderPayload.sender_mode === "own_domain" && senderPayload.verification_status !== "verified"){
        alert("Your sending domain is not verified yet. Please add the DNS records or use HireScore AI sender.")
        return
    }
    if(!senderPayload.reply_to || !senderPayload.reply_to.includes("@")){
        alert("Please set a valid reply-to email for the active sender.")
        openHireScoreSenderModal()
        return
    }
    localStorage.setItem("outreachSenderEmail", senderPayload.reply_to)
    setButtonLoading(button, true, "Sending...")

    try{
        let jobRes = await fetch(API + "/public-job/" + encodeURIComponent(jobId))
        let job = jobRes.ok ? await jobRes.json() : {}

        let res = await fetch(API + "/send-mail", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + localStorage.getItem("token")
            },
            body: JSON.stringify({
                email: email,
                name: name,
                job_id: jobId,
                job_title: jobTitle,
                recruiter_email: senderPayload.reply_to,
                recruiter_name: localStorage.getItem("username"),
                sender_mode: senderPayload.sender_mode,
                from_email: senderPayload.from_email,
                from_name: senderPayload.from_name,
                reply_to: senderPayload.reply_to,
                sender_domain: senderPayload.domain,
                verification_status: senderPayload.verification_status,
                hiring_manager: job.hiring_manager,
                company_name: job.company_name
            })
        })

        let data = await res.json()

        if(!res.ok || data.error){
            alert("Mail failed: " + (data.detail || data.error || "Email provider not configured"))
            return
        }

        alert("Mail sent successfully to " + email + (data.reply_to ? "\nReply-To: " + data.reply_to : ""))

        if(jobId){
            await loadCommunicationSplit(jobId)
            await loadCommunicationJobs()
        }
    }catch(err){
        alert("Mail failed. Please check backend email configuration.")
    }finally{
        setButtonLoading(button, false)
    }
}

async function sendAssessmentTest(candidateId, jobId){
    if(!candidateId || !jobId){
        alert("Candidate or job is missing.")
        return
    }

    let recruiterEmail = getReplySyncEmail()
    if(!recruiterEmail){
        alert("Recruiter email not found. Please login again.")
        return
    }

    let button = typeof event !== "undefined" ? event.currentTarget : null
    setButtonLoading(button, true, "Sending...")

    try{
        let res = await fetch(API + "/send-assessment-test", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({
                candidate_id: candidateId,
                job_id: jobId,
                recruiter_email: recruiterEmail
            })
        })

        let data = await res.json()
        if(!res.ok || data.error){
            let message = data.detail || data.error || "Google Forms/Gmail is not configured"
            if(res.status === 401 || /connect|gmail|google|forms/i.test(message)){
                offerGoogleReconnect("Test send failed: " + message)
                return
            }
            alert("Test send failed: " + message)
            return
        }

        alert(data.message || "Test sent successfully")
        await loadCommunicationSplit(jobId)
    }catch(err){
        alert("Test send failed. Please check Google Forms and Gmail configuration.")
    }finally{
        setButtonLoading(button, false)
    }
}

async function syncAssessmentResults(jobId, options = {}){
    let silent = options.silent === true
    let reload = options.reload !== false
    let button = typeof event !== "undefined" ? event.currentTarget : null

    if(!jobId){
        if(!silent) alert("Select job first")
        return
    }

    let recruiterEmail = getReplySyncEmail()
    if(!recruiterEmail){
        if(!silent) alert("Recruiter email not found. Please login again.")
        return
    }

    setButtonLoading(button, true, "Syncing...")

    try{
        let res = await fetch(API + "/sync-assessment-results", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({
                job_id: jobId,
                recruiter_email: recruiterEmail
            })
        })

        let data = await res.json()
        if(!res.ok || data.error){
            let message = data.detail || data.error || "Google Forms response access is not configured"
            if(!silent && (res.status === 401 || /connect|gmail|google|forms/i.test(message))){
                offerGoogleReconnect("Result sync failed: " + message)
                return
            }
            if(!silent) alert("Result sync failed: " + message)
            return
        }

        if(!silent) alert("Assessment results synced. Updated: " + (data.updated || 0))
        if(reload) await loadCommunicationSplit(jobId)
        return data
    }catch(err){
        if(!silent) alert("Result sync failed")
    }finally{
        setButtonLoading(button, false)
    }
}

async function moveCandidateToInterviewScheduling(candidateId, jobId){
    if(!candidateId || !jobId){
        alert("Candidate or job is missing.")
        return
    }

    let button = typeof event !== "undefined" ? event.currentTarget : null
    setButtonLoading(button, true, "Moving...")

    try{
        let res = await fetch(API + "/move-to-interview-scheduling", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({
                candidate_id: candidateId,
                job_id: jobId
            })
        })

        let data = await res.json()
        if(!res.ok || data.error){
            alert("Could not move candidate: " + (data.detail || data.error || "Test is not passed yet"))
            return
        }

        alert(data.message || "Candidate moved to interview scheduling")
        await loadCommunicationSplit(jobId)
    }catch(err){
        alert("Could not move candidate to interview scheduling")
    }finally{
        setButtonLoading(button, false)
    }
}

async function loadInterviewDashboard(){
    let table = document.getElementById("interviewDashboardTable")
    if(!table) return

    table.innerHTML = `<tr><td colspan="8" class="ats-empty-state">Loading interview pipeline...</td></tr>`

    try{
        let res = await fetch(API + "/interview-dashboard", {
            headers: authHeaders()
        })
        let data = await res.json()
        if(!res.ok || data.error){
            table.innerHTML = `<tr><td colspan="8" class="ats-empty-state">Could not load interview dashboard</td></tr>`
            return
        }

        interviewDashboardCandidates = Array.isArray(data.candidates) ? data.candidates : []
        populateInterviewFilters(interviewDashboardCandidates)
        renderInterviewDashboard()
    }catch(err){
        table.innerHTML = `<tr><td colspan="8" class="ats-empty-state">Could not load interview dashboard</td></tr>`
    }
}

function getInterviewRowModel(candidate){
    let status = candidate.interview_status || "Pending"
    if(status === "Interview Scheduling") status = "Pending"
    let scheduledAt = candidate.scheduled_at ? new Date(candidate.scheduled_at) : null
    let hasValidDate = scheduledAt && !Number.isNaN(scheduledAt.getTime())
    let dateValue = hasValidDate ? scheduledAt.toISOString().slice(0,10) : ""
    let dateTime = hasValidDate
        ? scheduledAt.toLocaleString([], {dateStyle:"medium", timeStyle:"short"})
        : "Awaiting slot"
    return {
        ...candidate,
        round: "Technical Screen",
        interviewer: candidate.company_name ? candidate.company_name + " hiring team" : "Hiring team",
        dateTime,
        dateValue,
        status,
        meetingType: candidate.meeting_url ? "Video" : "TBD"
    }
}

function openInterviewJoinLink(url){
    if(!url){
        alert("Join link is not attached yet. Click Schedule and add the meeting link.")
        return
    }
    window.open(url, "_blank", "noopener")
}

async function scheduleInterviewSlot(candidateId, jobId, currentLink = "", currentDateTime = ""){
    if(!candidateId || !jobId){
        alert("Candidate or job is missing.")
        return
    }

    let meetingUrl = prompt("Paste Google Meet / Zoom / Teams link", currentLink || "")
    if(meetingUrl === null) return
    meetingUrl = meetingUrl.trim()
    if(!meetingUrl){
        alert("Meeting link is required.")
        return
    }

    let defaultDate = ""
    if(currentDateTime){
        let parsed = new Date(currentDateTime)
        if(!Number.isNaN(parsed.getTime())){
            defaultDate = parsed.toISOString().slice(0,16)
        }
    }
    let scheduledAt = prompt("Interview date & time (YYYY-MM-DDTHH:mm). Leave blank if not fixed yet.", defaultDate)
    if(scheduledAt === null) return

    try{
        let res = await fetch(API + "/schedule-interview-slot", {
            method:"POST",
            headers: authHeaders(),
            body: JSON.stringify({
                candidate_id: candidateId,
                job_id: jobId,
                meeting_url: meetingUrl,
                scheduled_at: (scheduledAt || "").trim()
            })
        })
        let data = await res.json()
        if(!res.ok || data.error){
            alert("Could not save interview slot: " + (data.detail || data.error || "Invalid meeting details"))
            return
        }
        alert(data.message || "Interview slot saved")
        await loadInterviewDashboard()
    }catch(err){
        alert("Could not save interview slot")
    }
}

function populateInterviewFilters(candidates){
    let roleFilter = document.getElementById("interviewJobFilter")
    if(!roleFilter) return

    let currentValue = roleFilter.value
    let roles = [...new Set(candidates.map(c => c.job_title).filter(Boolean))].sort()
    roleFilter.innerHTML = `<option value="">All roles</option>` + roles.map(role => `
        <option value="${safeHtml(role)}">${safeHtml(role)}</option>
    `).join("")
    roleFilter.value = roles.includes(currentValue) ? currentValue : ""
}

function setInterviewStatusFilter(status, button){
    let input = document.getElementById("interviewStatusFilter")
    if(input) input.value = status
    document.querySelectorAll(".ats-filter-chip").forEach(chip => chip.classList.remove("is-active"))
    if(button) button.classList.add("is-active")
    renderInterviewDashboard()
}

function interviewEmptyState(title, body, actionText="Refresh"){
    return `
        <div class="ats-interview-empty-state">
            <div class="ats-empty-mark">ID</div>
            <h4>${safeHtml(title)}</h4>
            <p>${safeHtml(body)}</p>
            <button onclick="loadInterviewDashboard()" class="ats-interview-secondary-btn">${safeHtml(actionText)}</button>
        </div>
    `
}

function interviewCard(candidate){
    let initial = safeHtml((candidate.name || "C").slice(0,1).toUpperCase())
    let profileId = registerCandidateProfile({
        ...candidate,
        full_name: candidate.name || candidate.full_name,
        name: candidate.name || candidate.full_name,
        designation: candidate.job_title,
        status: candidate.status
    })
    return `
        <article class="ats-workflow-card">
            <div class="ats-workflow-card-top">
                <button type="button" class="ats-candidate-avatar ats-profile-open-avatar" data-profile-candidate-id="${safeHtml(profileId)}" title="Open candidate profile">${initial}</button>
                <div>
                    <h4><button type="button" class="ats-candidate-name-link" data-profile-candidate-id="${safeHtml(profileId)}">${safeHtml(candidate.name || "Candidate")}</button></h4>
                    <p>${safeHtml(candidate.job_title || "Open role")}</p>
                </div>
            </div>
            <div class="ats-workflow-card-meta">
                <span>${safeHtml(candidate.round)}</span>
                <span>${safeHtml(candidate.dateTime)}</span>
            </div>
            <div class="ats-workflow-card-footer">
                <span class="ats-interview-status ${candidate.status === "Pending" ? "is-pending" : candidate.status === "Completed" ? "is-complete" : "is-rescheduled"}">${safeHtml(candidate.status)}</span>
                <div class="ats-card-actions">
                    ${candidate.meeting_url ? `
                        <button onclick="openInterviewJoinLink('${safeJs(candidate.meeting_url)}')" title="Join">Join</button>
                    ` : `
                        <button onclick="scheduleInterviewSlot('${safeJs(candidate.id)}','${safeJs(candidate.job_id)}')" title="Schedule">Schedule</button>
                    `}
                    <button onclick="scheduleInterviewSlot('${safeJs(candidate.id)}','${safeJs(candidate.job_id)}','${safeJs(candidate.meeting_url || "")}','${safeJs(candidate.scheduled_at || "")}')" title="Reschedule">Reschedule</button>
                    <button onclick="alert('Interview details for ${safeJs(candidate.name || "Candidate")}')" title="View">View</button>
                    <button onclick="alert('Feedback workflow is ready for this candidate.')" title="Feedback">Feedback</button>
                </div>
            </div>
        </article>
    `
}

function renderInterviewDashboard(){
    let table = document.getElementById("interviewDashboardTable")
    if(!table) return

    let rows = interviewDashboardCandidates.map(getInterviewRowModel)
    let totalBox = document.getElementById("interviewTotalCount")
    let todayBox = document.getElementById("interviewTodayCount")
    let pendingBox = document.getElementById("interviewPendingCount")
    let completedBox = document.getElementById("interviewCompletedCount")
    let rescheduledBox = document.getElementById("interviewRescheduledCount")

    if(totalBox) totalBox.innerText = rows.length
    if(todayBox) todayBox.innerText = rows.filter(c => c.dateValue === new Date().toISOString().slice(0,10)).length
    if(pendingBox) pendingBox.innerText = rows.filter(c => c.status === "Pending").length
    if(completedBox) completedBox.innerText = rows.filter(c => c.status === "Completed").length
    if(rescheduledBox) rescheduledBox.innerText = rows.filter(c => c.status === "Rescheduled").length

    let jobFilter = document.getElementById("interviewJobFilter")?.value || ""
    let statusFilter = document.getElementById("interviewStatusFilter")?.value || ""
    let roundFilter = document.getElementById("interviewRoundFilter")?.value || ""
    let dateFilter = document.getElementById("interviewDateFilter")?.value || ""
    let searchFilter = (document.getElementById("interviewSearchFilter")?.value || "").trim().toLowerCase()

    let filtered = rows.filter(c => {
        let searchable = `${c.name || ""} ${c.email || ""} ${c.job_title || ""}`.toLowerCase()
        if(jobFilter && c.job_title !== jobFilter) return false
        if(statusFilter && c.status !== statusFilter) return false
        if(roundFilter && c.round !== roundFilter) return false
        if(dateFilter && c.dateValue !== dateFilter) return false
        if(searchFilter && !searchable.includes(searchFilter)) return false
        return true
    })

    let todayRows = filtered.filter(c => c.dateValue === new Date().toISOString().slice(0,10))
    let scheduledRows = filtered.filter(c => c.status === "Scheduled")
    let pendingRows = filtered.filter(c => c.status === "Pending")
    let completedRows = filtered.filter(c => c.status === "Completed")
    let rescheduledRows = filtered.filter(c => c.status === "Rescheduled")

    let workflowGroups = [
        ["workflowTodayList", "workflowTodayCount", todayRows, "No interviews today", "When slots are confirmed for today, they will appear here."],
        ["workflowScheduledList", "workflowScheduledCount", scheduledRows, "No scheduled interviews", "Confirmed future interview rounds will show in this lane."],
        ["workflowPendingList", "workflowPendingCount", pendingRows, "Needs scheduling", "Candidates waiting for recruiter action are shown here."],
        ["workflowCompletedList", "workflowCompletedCount", completedRows, "No completed rounds", "Finished interviews will be tracked here."],
        ["workflowRescheduledList", "workflowRescheduledCount", rescheduledRows, "No reschedules", "Changed interview slots will appear here."]
    ]

    workflowGroups.forEach(([listId, countId, items, title, body]) => {
        let list = document.getElementById(listId)
        let count = document.getElementById(countId)
        if(count) count.innerText = items.length
        if(list) list.innerHTML = items.length ? items.map(interviewCard).join("") : interviewEmptyState(title, body)
    })

    table.innerHTML = filtered.length ? filtered.map(c => {
        let profileId = registerCandidateProfile({
            ...c,
            full_name: c.name || c.full_name,
            name: c.name || c.full_name,
            designation: c.job_title,
            status: c.status
        })
        return `
        <tr>
            <td>
                <button type="button" class="ats-table-candidate ats-candidate-name-link" data-profile-candidate-id="${safeHtml(profileId)}">${safeHtml(c.name || "Candidate")}</button>
                <small class="ats-muted-line">${safeHtml(c.email || "")}</small>
            </td>
            <td>
                <span class="ats-ellipsis" title="${safeHtml(c.job_title || "")}">${safeHtml(c.job_title || "Open role")}</span>
                <small class="ats-muted-line">${safeHtml(c.company_name || "")}</small>
            </td>
            <td><span class="ats-round-pill">${safeHtml(c.round)}</span></td>
            <td><span class="ats-ellipsis" title="${safeHtml(c.interviewer)}">${safeHtml(c.interviewer)}</span></td>
            <td><span class="ats-date-pill">${safeHtml(c.dateTime)}</span></td>
            <td><span class="ats-interview-status ${c.status === "Pending" ? "is-pending" : c.status === "Completed" ? "is-complete" : "is-rescheduled"}">${safeHtml(c.status)}</span></td>
            <td><span class="ats-meeting-pill">${safeHtml(c.meetingType)}</span></td>
            <td>
                <div class="ats-interview-actions">
                    ${c.meeting_url ? `
                        <button onclick="openInterviewJoinLink('${safeJs(c.meeting_url)}')" class="ats-interview-secondary-btn">Join</button>
                    ` : `
                        <button onclick="scheduleInterviewSlot('${safeJs(c.id)}','${safeJs(c.job_id)}')" class="ats-interview-primary-small">Schedule</button>
                    `}
                    <button onclick="alert('Interview details for ${safeJs(c.name || "Candidate")}')" class="ats-interview-secondary-btn">Details</button>
                    <button onclick="scheduleInterviewSlot('${safeJs(c.id)}','${safeJs(c.job_id)}','${safeJs(c.meeting_url || "")}','${safeJs(c.scheduled_at || "")}')" class="ats-interview-primary-small">Reschedule</button>
                </div>
            </td>
        </tr>
    `
    }).join("") : `<tr><td colspan="8" class="ats-empty-state">No interviews match the selected filters</td></tr>`
}

async function loadCommunicationSplitLegacy(jobId){

    let res = await fetch(API + "/communication-filter?job_id=" + jobId)
    let data = await res.json()

    let topHTML = ""              // * NOT CONTACTED
    let interestedHTML = ""
    let notInterestedHTML = ""
    let pendingHTML = ""
    let legacyCommName = candidate => candidateProfileNameButton({
        ...candidate,
        full_name: candidate.name || candidate.full_name,
        name: candidate.name || candidate.full_name,
        final_score: candidate.final_score ?? candidate.score,
        status: candidate.status,
        designation: window.currentJobTitle
    }, "ats-candidate-name-link ats-legacy-name-link")

    // OK Interested
    data.interested.forEach(c => {
        interestedHTML += `
        <tr>
            <td>${legacyCommName(c)}</td>
            <td>${c.email}</td>
            <td style="color:green;">${c.status}</td>
        </tr>
        `
    })

    // Error: Not Interested
    data.not_interested.forEach(c => {
        notInterestedHTML += `
        <tr>
            <td>${legacyCommName(c)}</td>
            <td>${c.email}</td>
            <td style="color:red;">${c.status}</td>
        </tr>
        `
    })

    // * SPLIT LOGIC
    data.pending.forEach(c => {

        // pending NOT CONTACTED -> TOP TABLE
        if(c.status === "Not Contacted"){

            topHTML += `
            <tr>
                <td>${legacyCommName(c)}</td>
                <td>${c.email}</td>
                <td style="color:#f59e0b; font-weight:600;">
                    ${c.status}
                </td>
                <td>
                    <button onclick="sendMail('${c.email}','${c.name}','${window.currentJobTitle}','${jobId}')"
                    style="background:#2563eb;color:white;padding:6px 10px;border-radius:6px;">
                    Send Mail
                    </button>
                </td>
            </tr>
            `
        }

        // pending PENDING
        else{
            pendingHTML += `
            <tr>
                <td>${legacyCommName(c)}</td>
                <td>${c.email}</td>
                <td style="color:#6366f1; font-weight:600;">
                    ${c.status}
                </td>
            </tr>
            `
        }
    })

    // * FINAL RENDER
    document.getElementById("communicationResultsTable").innerHTML = topHTML
    document.getElementById("pendingTable").innerHTML = pendingHTML
    document.getElementById("interestedTable").innerHTML = interestedHTML
    document.getElementById("notInterestedTable").innerHTML = notInterestedHTML
}

function googleLoginLegacy(){
window.location.href = API + "/google-login"
}


async function loadCommunicationCandidatesByJob(jobId){

let res = await fetch(API + "/communication?job_id=" + jobId)
let data = await res.json()


let container = document.getElementById("communicationTable")

if(!container) return

container.innerHTML = ""

if(data.length === 0){
    container.innerHTML = "<p>No candidates</p>"
    return
}

data.forEach(c => {

container.innerHTML += `

<div style="border:1px solid #ddd; padding:10px; margin-top:5px; border-radius:6px">

<b>${c.name || ""}</b><br>
${c.email || ""}<br>
Mail: ${c.mail_status || "Not Sent"}<br>
Response: ${c.response_status || "Pending"}

</div>

`

})
}


async function moveAllToCommunicationLegacy(){

    let jobId = document.getElementById("shortlistJobSelect").value

    if(!jobId){
        alert("Select job first")
        return
    }

    if(!confirm("Move all shortlisted candidates to communication?")){
        return
    }

    let res = await fetch(API + "/move-to-communication?job_id=" + jobId, {
        method: "POST"
    })

    let data = await res.json()

    if(data.error){
        alert("Error: " + data.error)
        return
    }

    alert("OK " + data.message)

    // * EXISTING
    loadShortlistedCandidates()

    // ** YEH ADD KARNA HAI (MOST IMPORTANT)
    loadCommunicationSplit(jobId)

}
async function loadCommunicationJobDropdown(){

let res = await fetch(API + "/jobs", {
    headers: {
        "Authorization": "Bearer " + localStorage.getItem("token")
    }
})
let jobs = await res.json()

let select = document.getElementById("communicationJobSelect")

if(!select) return

select.innerHTML = `<option value="">SELECT JOB</option>`

jobs
.filter(job => job.is_active === true)
.forEach(job => {

select.innerHTML += `
<option value="${job.id}">
${job.job_title}
</option>
`

})
}


async function loadCommunicationCandidates(){

let jobId = document.getElementById("communicationJobSelect").value

if(!jobId){
    alert("Select job")
    return
}

let res = await fetch(API + "/communication?job_id=" + jobId)
let data = await res.json()

let table = document.getElementById("communicationTableBody")

table.innerHTML = ""

data.forEach(c => {
    let profileName = candidateProfileNameButton({
        ...c,
        full_name: c.name || c.full_name,
        name: c.name || c.full_name,
        status: c.status
    }, "ats-candidate-name-link ats-legacy-name-link")

    let row = `
    <tr>
        <td>${profileName}</td>
        <td>${c.email}</td>
        <td>${c.status}</td>
        <td>-</td>
    </tr>
    `

    table.innerHTML += row
})
}

function renderCommTable(candidates){

let table = document.getElementById("commTable")
table.innerHTML = ""

candidates.forEach(c => {
let profileName = candidateProfileNameButton({
...c,
full_name: c.name || c.full_name,
name: c.name || c.full_name,
status: c.status
}, "ats-candidate-name-link ats-legacy-name-link")

table.innerHTML += `

<tr>
<td>${profileName}</td>
<td>${c.email}</td>
<td>${c.status}</td>

<td>
<button onclick="sendStage1('${c.id}')">
Send Mail
</button>
</td>

</tr>

`
})
}

async function loadShortlistedCandidates(){

    let jobSelect = document.getElementById("shortlistJobSelect")
    let table = document.getElementById("shortlistTable")
    let jobId = jobSelect ? jobSelect.value : ""

    if(!table) return

    if(!jobId){
        table.innerHTML = `
        <tr>
            <td colspan="18" class="ats-empty-state">Select a job to view shortlisted candidates</td>
        </tr>
        `
        return
    }

    table.innerHTML = `
    <tr>
        <td colspan="18" class="ats-empty-state">Loading shortlisted candidates...</td>
    </tr>
    `

    let minScore = getNumericInputValue("shortlistMinScore")
    let url = API + "/shortlisted?job_id=" + encodeURIComponent(jobId)

    if(minScore !== null){
        url += "&min_score=" + encodeURIComponent(minScore)
    }

    try{
    let res = await fetch(url)
    if(!res.ok){
        throw new Error(await res.text() || "Shortlist API failed")
    }
    let data = await res.json()
    data = Array.isArray(data) ? data : []
    currentShortlistResults = data.map(shortlistCandidateModel)

    if(data.length === 0){
        currentShortlistResults = []
        table.innerHTML = `
        <tr>
            <td colspan="18" class="ats-empty-state">
                ${minScore === null ? "No shortlisted candidates yet for this job" : "No candidates match this score filter"}
            </td>
        </tr>
        `
        return
    }

    table.innerHTML = data.map((c, index) => {
        let score = c.score ?? c.final_score ?? 0
        let candidateName = c.name || c.full_name || "Unnamed Candidate"
        let candidateEmail = c.email || ""
        let candidateInitial = candidateInitials(candidateName)
        let status = c.status || "Shortlisted"
        let profileId = registerCandidateProfile({
            ...c,
            full_name: candidateName,
            name: candidateName,
            email: candidateEmail,
            final_score: score,
            total_experience_years: c.total_experience_years ?? c.experience,
            last_company_name: c.last_company_name || c.last_company,
            key_skills: c.key_skills || c.matched_skills
        })
        return `
        <tr class="ats-shortlist-row">
            <td><span class="ats-shortlist-rank">#${index + 1}</span></td>
            <td>
                <div class="ats-shortlist-candidate">
                    <button type="button" class="ats-shortlist-avatar ats-profile-open-avatar" data-profile-candidate-id="${safeHtml(profileId)}" title="Open candidate profile">${safeHtml(candidateInitial)}</button>
                    <div>
                        <button type="button" class="ats-candidate-name-link ats-shortlist-name-link" data-profile-candidate-id="${safeHtml(profileId)}" title="${safeHtml(candidateName)}">${safeHtml(candidateName)}</button>
                        <small>${safeHtml(status)}</small>
                    </div>
                </div>
            </td>
            <td><span class="ats-ellipsis ats-shortlist-email" title="${safeHtml(candidateEmail)}">${safeHtml(candidateEmail)}</span></td>
            <td class="hidden">${safeHtml(c.phone || "")}</td>
            <td><span class="ats-shortlist-location">${safeHtml(c.location || "Location not listed")}</span></td>
            <td class="hidden">${safeHtml(c.designation || "")}</td>
            <td><span class="ats-shortlist-experience">${safeHtml(formatExperience(c.experience || c.total_experience_years) || "")}</span></td>
            <td class="hidden">${safeHtml(c.last_company || "")}</td>
            <td class="hidden">${safeHtml(c.last_working_date || "")}</td>
            <td class="hidden">${safeHtml(c.matched_skills || "")}</td>
            <td class="hidden">${safeHtml(cleanedCandidateMissingSkills(c).join(", "))}</td>
            <td class="hidden">${safeHtml(c.skill_match_percent || "")}</td>
            <td class="hidden">${safeHtml(c.industry || "")}</td>
            <td class="hidden">${safeHtml(c.domain || "")}</td>
            <td class="hidden">${safeHtml(c.education || "")}</td>
            <td class="hidden">${safeHtml(status)}</td>
            <td><span class="ats-shortlist-score">${safeHtml(formatScore(score))}</span></td>
            <td>
                <button onclick="shortlistCandidate('${safeJs(c.id)}', '${safeJs(c.status || "Shortlisted")}')"
                class="shortlist-row-btn ats-shortlist-row-btn is-review">
                    Shortlist
                </button>
                <button onclick="removeShortlist('${safeJs(c.id)}')"
                class="shortlist-row-btn ats-shortlist-row-btn is-remove">
                    Remove
                </button>
            </td>
        </tr>
        `
    }).join("")
    }catch(error){
        currentShortlistResults = []
        table.innerHTML = `
        <tr>
            <td colspan="18" class="ats-empty-state">
                Could not load shortlisted candidates. ${safeHtml(error.message || "Please refresh and try again.")}
            </td>
        </tr>
        `
    }
}

async function loadCommunicationSplit(jobId){
    window.currentJobId = jobId

    let topTable = document.getElementById("communicationResultsTable")
    let pendingTable = document.getElementById("pendingTable")
    let interestedTable = document.getElementById("interestedTable")
    let notInterestedTable = document.getElementById("notInterestedTable")

    if(!topTable || !pendingTable || !interestedTable || !notInterestedTable) return

    topTable.innerHTML = `<tr><td colspan="6" class="ats-empty-state">Loading communication candidates...</td></tr>`
    pendingTable.innerHTML = ""
    interestedTable.innerHTML = ""
    notInterestedTable.innerHTML = ""

    let autoSyncKey = String(jobId || "")
    window.gmailAutoSyncJobs = window.gmailAutoSyncJobs || {}
    let lastAutoSync = window.gmailAutoSyncJobs[autoSyncKey] || 0
    if(localStorage.getItem("gmailConnected") === "true" && Date.now() - lastAutoSync > 60000){
        window.gmailAutoSyncJobs[autoSyncKey] = Date.now()
        await syncGmailReplies({ silent: true, reload: false })
    }

    window.assessmentAutoSyncJobs = window.assessmentAutoSyncJobs || {}
    let lastAssessmentSync = window.assessmentAutoSyncJobs[autoSyncKey] || 0
    if(localStorage.getItem("gmailConnected") === "true" && Date.now() - lastAssessmentSync > 60000){
        window.assessmentAutoSyncJobs[autoSyncKey] = Date.now()
        await syncAssessmentResults(jobId, { silent: true, reload: false })
    }

    let res = await fetch(API + "/communication-filter?job_id=" + encodeURIComponent(jobId))
    let data = await res.json()

    let pending = Array.isArray(data.pending) ? data.pending : []
    let interested = Array.isArray(data.interested) ? data.interested : []
    let notInterested = Array.isArray(data.not_interested) ? data.not_interested : []

    let notContactedRows = pending.filter(c => c.status === "Not Contacted")
    let pendingRows = pending.filter(c => c.status !== "Not Contacted")
    let setCommCount = (id, count, label = "") => {
        let el = document.getElementById(id)
        if(el) el.innerText = label ? `${count} ${label}` : count
    }

    setCommCount("commFirstContactCount", notContactedRows.length)
    setCommCount("commInterestedCount", interested.length)
    setCommCount("commPendingCount", pendingRows.length)
    setCommCount("commNotInterestedCount", notInterested.length)
    setCommCount("commFirstContactBadge", notContactedRows.length, notContactedRows.length === 1 ? "candidate" : "candidates")
    setCommCount("commInterestedBadge", interested.length, interested.length === 1 ? "candidate" : "candidates")
    setCommCount("commPendingBadge", pendingRows.length, pendingRows.length === 1 ? "candidate" : "candidates")
    setCommCount("commNotInterestedBadge", notInterested.length, notInterested.length === 1 ? "candidate" : "candidates")
    let communicationCandidateNameCell = candidate => {
        let profileId = registerCandidateProfile({
            ...candidate,
            full_name: candidate.name || candidate.full_name,
            name: candidate.name || candidate.full_name,
            final_score: candidate.final_score ?? candidate.score,
            status: candidate.status,
            designation: candidate.job_title || window.currentJobTitle
        })
        let label = candidate.name || candidate.full_name || "Candidate"
        return `<button type="button" class="ats-candidate-name-link ats-comm-name-link ats-ellipsis" data-profile-candidate-id="${safeHtml(profileId)}" title="${safeHtml(label)}">${safeHtml(label)}</button>`
    }

    topTable.innerHTML = notContactedRows.length ? notContactedRows.map(c => `
        <tr>
            <td>${communicationCandidateNameCell(c)}</td>
            <td><span class="ats-ellipsis" title="${safeHtml(c.email)}">${safeHtml(c.email)}</span></td>
            <td><span class="ats-score-pill">${safeHtml(c.final_score ?? 0)}</span></td>
            <td><span class="ats-next-step">${safeHtml(c.next_step || "Send outreach")}</span></td>
            <td><span class="ats-status-pill ats-status-warn">${safeHtml(c.status)}</span></td>
            <td>
                <button onclick="sendMail('${safeJs(c.email)}','${safeJs(c.name)}','${safeJs(window.currentJobTitle)}','${safeJs(jobId)}')"
                class="ats-send-btn bg-blue-600 text-white px-3 py-1 rounded text-sm">
                    Send Mail
                </button>
            </td>
        </tr>
    `).join("") : `<tr><td colspan="6" class="ats-empty-state">No candidates waiting for first contact</td></tr>`

    pendingTable.innerHTML = pendingRows.length ? pendingRows.map(c => `
        <tr>
            <td>${communicationCandidateNameCell(c)}</td>
            <td><span class="ats-ellipsis" title="${safeHtml(c.email)}">${safeHtml(c.email)}</span></td>
            <td><span class="ats-score-pill">${safeHtml(c.final_score ?? 0)}</span></td>
            <td><span class="ats-next-step">${safeHtml(c.next_step || "Await response")}</span></td>
            <td><span class="ats-status-pill ats-status-info">${safeHtml(c.status)}</span></td>
            <td>
                <div class="ats-response-actions ats-response-actions-row">
                    <button onclick="updateCommunicationResponse('${safeJs(c.id)}','Interested')" class="ats-response-btn is-interested">
                        Interested
                    </button>
                    <button onclick="updateCommunicationResponse('${safeJs(c.id)}','Not Interested')" class="ats-response-btn is-not-interested">
                        Not Interested
                    </button>
                </div>
            </td>
        </tr>
    `).join("") : `<tr><td colspan="6" class="ats-empty-state">No pending responses</td></tr>`

    interestedTable.innerHTML = interested.length ? interested.map(c => `
        <tr>
            <td>${communicationCandidateNameCell(c)}</td>
            <td><span class="ats-ellipsis" title="${safeHtml(c.email)}">${safeHtml(c.email)}</span></td>
            <td><span class="ats-score-pill">${safeHtml(c.final_score ?? 0)}</span></td>
            <td>
                ${c.test_status ? `
                    <span class="ats-next-step">${safeHtml(c.test_status)}</span>
                ` : `
                    <button onclick="sendAssessmentTest('${safeJs(c.id)}','${safeJs(jobId)}')" class="ats-send-btn bg-blue-600 text-white px-3 py-1 rounded text-sm">
                        Send Test
                    </button>
                `}
            </td>
            <td>
                ${c.test_percentage != null ? `
                    <span class="ats-test-result ${c.test_result_status === "Passed" ? "is-pass" : "is-review"}">
                        ${safeHtml(c.test_result_status || "Test Done")} - ${safeHtml(c.test_score ?? 0)}/${safeHtml(c.test_max_score ?? 0)} (${safeHtml(c.test_percentage)}%)
                    </span>
                ` : c.test_status ? `
                    <button onclick="syncAssessmentResults('${safeJs(jobId)}')" class="ats-mini-action-btn">
                        Sync Result
                    </button>
                ` : `
                    <span class="ats-next-step">Not sent</span>
                `}
            </td>
            <td>
                ${c.test_percentage != null ? `
                    <button onclick="moveCandidateToInterviewScheduling('${safeJs(c.id)}','${safeJs(jobId)}')" class="ats-pipeline-btn is-ready">
                        ${c.test_result_status === "Passed" ? "Interview Scheduling" : "Review & Schedule"}
                    </button>
                ` : `
                    <button class="ats-pipeline-btn is-locked" disabled>
                        Interview Pipeline
                    </button>
                `}
            </td>
            <td><span class="ats-status-pill ats-status-success">${safeHtml(c.status)}</span></td>
        </tr>
    `).join("") : `<tr><td colspan="7" class="ats-empty-state">No interested candidates yet</td></tr>`

    notInterestedTable.innerHTML = notInterested.length ? notInterested.map(c => `
        <tr>
            <td>${communicationCandidateNameCell(c)}</td>
            <td><span class="ats-ellipsis" title="${safeHtml(c.email)}">${safeHtml(c.email)}</span></td>
            <td><span class="ats-score-pill">${safeHtml(c.final_score ?? 0)}</span></td>
            <td>
                <button onclick="dropCommunicationCandidate('${safeJs(c.id)}','${safeJs(jobId)}')" class="ats-response-btn is-not-interested">
                    Drop Candidate
                </button>
            </td>
            <td><span class="ats-status-pill ats-status-danger">${safeHtml(c.status)}</span></td>
        </tr>
    `).join("") : `<tr><td colspan="5" class="ats-empty-state">No not-interested responses</td></tr>`
}

async function moveAllToCommunication(){

    let select = document.getElementById("shortlistJobSelect")
    let jobId = select ? select.value : ""
    let trigger = event && event.currentTarget ? event.currentTarget : null

    if(!jobId){
        alert("Select job first")
        return
    }

    if(!confirm("Move all shortlisted candidates to communication?")){
        return
    }

    setButtonLoading(trigger, true, "Moving...")

    try{
        let res = await fetch(API + "/move-to-communication?job_id=" + encodeURIComponent(jobId), {
            method: "POST"
        })

        let data = await res.json()

        if(!res.ok || data.error){
            alert("Could not move candidates")
            return
        }

        alert(data.message)
        await refreshRecruiterWorkflow(jobId)
    }finally{
        setButtonLoading(trigger, false)
    }
}

async function loadCommunicationJobs(){

    let res = await fetch(API + "/jobs", {
        headers: {
            "Authorization": "Bearer " + localStorage.getItem("token")
        }
    })
    let jobs = await res.json()
    jobs = Array.isArray(jobs) ? jobs : []

    let container = document.getElementById("communicationJobsContainer")

    if(!container) return

    let activeJobs = jobs.filter(j => j.is_active === true)
    let totalApplicants = activeJobs.reduce((sum, job) => sum + (Number(job.total_applicants) || 0), 0)
    let communicationTotal = activeJobs.reduce((sum, job) => sum + (Number(job.communication_count) || 0), 0)
    let bestScore = activeJobs.reduce((max, job) => Math.max(max, Number(job.top_score) || 0), 0)

    let activeEl = document.getElementById("outreachActiveRoles")
    let applicantsEl = document.getElementById("outreachApplicants")
    let queueEl = document.getElementById("outreachQueueCount")
    let bestEl = document.getElementById("outreachBestScore")
    let metaEl = document.getElementById("outreachRoleMeta")

    if(activeEl) activeEl.innerText = activeJobs.length
    if(applicantsEl) applicantsEl.innerText = totalApplicants
    if(queueEl) queueEl.innerText = communicationTotal
    if(bestEl) bestEl.innerText = bestScore
    if(metaEl) metaEl.innerText = `${activeJobs.length} active roles`

    if(activeJobs.length === 0){
        container.innerHTML = `<div class="ats-empty-state">No active jobs available for communication</div>`
        return
    }

    container.innerHTML = activeJobs.map(job => `
    <article class="ats-outreach-role-card">
        <div class="ats-outreach-card-top">
            <span class="ats-outreach-role-icon">CM</span>
            <span class="ats-outreach-status">Active</span>
        </div>

        <div class="ats-outreach-role-title">
            <h3 title="${safeHtml(job.job_title)}">${safeHtml(job.job_title || "Untitled Role")}</h3>
            <p title="${safeHtml(job.company_name)}">${safeHtml(job.company_name || "Company not specified")}</p>
        </div>

        <div class="ats-outreach-meta-grid">
            <span><strong>Location</strong>${safeHtml(job.location || "N/A")}</span>
            <span><strong>Salary</strong>${safeHtml(job.salary_range || "Not specified")}</span>
            <span><strong>Type</strong>${safeHtml(job.job_type || "Full Time")}</span>
        </div>

        <p class="ats-outreach-description">${safeHtml(shortText(job.jd_text || "No description added yet.", 145))}</p>

        <button
        onclick="openCommunicationPage('${safeJs(job.id)}', '${safeJs(job.job_title)}')"
        class="ats-outreach-view-btn">
            View Candidates
        </button>

        <div class="ats-outreach-card-footer">
            <span>Applicants <strong>${safeHtml(job.total_applicants || 0)}</strong></span>
            <span>Queue <strong>${safeHtml(job.communication_count || 0)}</strong></span>
            <span>Top Score <strong>${safeHtml(job.top_score || 0)}</strong></span>
        </div>
    </article>
    `).join("")
}


window.onload = function(){


    let returnPage = localStorage.getItem("oauthReturnPage")
    let returnJobId = localStorage.getItem("oauthReturnJobId") || localStorage.getItem("lastCommunicationJobId")
    let returnJobTitle = localStorage.getItem("oauthReturnJobTitle") || localStorage.getItem("lastCommunicationJobTitle") || "Selected Role"

    localStorage.removeItem("oauthReturnPage")
    localStorage.removeItem("oauthReturnJobId")
    localStorage.removeItem("oauthReturnJobTitle")

    if(returnPage === "communicationResults" && returnJobId){
        openCommunicationPage(returnJobId, returnJobTitle)
        return
    }

    if(returnPage === "communication"){
        showPage("communication")
        return
    }

    checkLogin()
    showPage("dashboard")
    bindJDAutofill()

}






