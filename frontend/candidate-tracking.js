function trackSafe(value){
    return String(value ?? "")
}

function trackText(id, value, fallback="-"){
    let el = document.getElementById(id)
    if(el) el.innerText = value || fallback
}

function normalizeTimeline(timeline, currentStage){
    let stages = ["Applied", "Screening", "Shortlisted", "Communication", "Interview", "Selected"]
    let incoming = Array.isArray(timeline) ? timeline : []
    let incomingStages = incoming.map(item => item.stage)
    let stageList = stages.some(stage => incomingStages.includes(stage)) ? stages : incomingStages

    if(currentStage && !stageList.includes(currentStage)){
        let insertAt = currentStage === "Communication" ? 3 : Math.max(stageList.length - 1, 0)
        stageList = [...stageList.slice(0, insertAt), currentStage, ...stageList.slice(insertAt)]
    }

    let activeIndex = stageList.indexOf(currentStage)
    if(activeIndex < 0) activeIndex = incoming.findIndex(item => item.active)
    if(activeIndex < 0) activeIndex = 0

    return stageList.map((stage, index) => ({
        stage,
        done: index <= activeIndex,
        active: index === activeIndex
    }))
}

function renderTimeline(timeline, currentStage){
    let box = document.getElementById("timeline")
    if(!box) return

    box.innerHTML = normalizeTimeline(timeline, currentStage).map(item => `
        <div class="track-step ${item.done ? "is-done" : ""} ${item.active ? "is-active" : ""}">
            <div class="track-dot"></div>
            <div>
                <strong>${trackSafe(item.stage)}</strong>
                <span>${item.active ? "Current stage" : item.done ? "Completed" : "Waiting"}</span>
            </div>
        </div>
    `).join("")
}

function candidateInitials(name){
    let parts = trackSafe(name).trim().split(/\s+/).filter(Boolean)
    if(!parts.length) return "AI"
    return parts.slice(0,2).map(part => part[0].toUpperCase()).join("")
}

function firstValue(...values){
    for(let value of values){
        if(value !== null && value !== undefined && value !== "") return value
    }
    return ""
}

function loadTrackingFallback(candidateId){
    try{
        let raw = sessionStorage.getItem("candidateTrackingFallback")
        if(!raw) return {}
        let parsed = JSON.parse(raw)
        return parsed.id === candidateId ? parsed : {}
    }catch(err){
        return {}
    }
}

async function loadCommunicationSnapshot(data){
    if(!data.job_id) return {}
    try{
        let res = await fetch(API + "/communication-filter?job_id=" + encodeURIComponent(data.job_id))
        if(!res.ok) return {}
        let snapshot = await res.json()
        let rows = [
            ...(Array.isArray(snapshot.pending) ? snapshot.pending : []),
            ...(Array.isArray(snapshot.interested) ? snapshot.interested : []),
            ...(Array.isArray(snapshot.not_interested) ? snapshot.not_interested : [])
        ]
        let email = trackSafe(data.email).trim().toLowerCase()
        return rows.find(row => row.id === data.id || trackSafe(row.email).trim().toLowerCase() === email) || {}
    }catch(err){
        return {}
    }
}

async function loadCandidateTracking(){
    let params = new URLSearchParams(window.location.search)
    let token = params.get("token")
    let candidateId = params.get("candidate_id")
    let state = document.getElementById("trackingState")
    let content = document.getElementById("trackingContent")

    if(!token && !candidateId){
        if(state) state.innerText = "Candidate tracking link is missing."
        return
    }

    let fallback = candidateId ? loadTrackingFallback(candidateId) : {}

    try{
        let endpoint = token
            ? API + "/candidate/track-token/" + encodeURIComponent(token)
            : API + "/candidate/track/" + encodeURIComponent(candidateId)
        let res = await fetch(endpoint)
        let data = await res.json()
        if(token && data && data.id){
            fallback = loadTrackingFallback(data.id)
        }
        if(!res.ok || data.error){
            if(Object.keys(fallback).length){
                data = fallback
            }else{
                if(state) state.innerText = data.error || "Could not load candidate tracking."
                return
            }
        }

        data = {
            ...fallback,
            ...data,
            job_id: firstValue(data.job_id, fallback.job_id),
            name: firstValue(data.name, fallback.name),
            email: firstValue(data.email, fallback.email),
            phone: firstValue(data.phone, fallback.phone),
            location: firstValue(data.location, fallback.location),
            job_title: firstValue(data.job_title, fallback.job_title),
            company_name: firstValue(data.company_name, fallback.company_name),
            final_score: firstValue(data.final_score, fallback.final_score, 0),
            confidence_score: firstValue(data.confidence_score, fallback.confidence_score),
            status: firstValue(data.status, fallback.status),
            designation: firstValue(data.designation, fallback.designation),
            experience: firstValue(data.experience, fallback.experience),
            current_stage: firstValue(data.current_stage, data.status, fallback.status, "Applied"),
            mail_status: firstValue(data.mail_status, fallback.mail_status, "Not Contacted"),
            response_status: firstValue(data.response_status, fallback.response_status, "Pending")
        }

        let communicationSnapshot = await loadCommunicationSnapshot(data)
        data = {
            ...data,
            mail_status: firstValue(communicationSnapshot.mail_status, data.mail_status),
            response_status: firstValue(communicationSnapshot.response_status, communicationSnapshot.status, data.response_status),
            current_stage: data.current_stage === "Communication" || communicationSnapshot.id ? "Communication" : data.current_stage
        }

        if((!data.mail_status || data.mail_status === "Not Contacted") && data.response_status && data.response_status !== "Pending"){
            data.mail_status = "Mail Sent"
        }
        if((!data.mail_status || data.mail_status === "Not Contacted") && data.current_stage === "Communication"){
            data.mail_status = "Mail Sent"
        }

        trackText("candidateName", data.name, "Candidate")
        trackText("candidateSubtitle", `${data.job_title || "Open role"}${data.company_name ? " at " + data.company_name : ""}`, "Candidate pipeline")
        trackText("currentStage", data.current_stage)
        trackText("heroStage", "Stage: " + (data.current_stage || "-"))
        trackText("heroScore", "Score: " + (data.final_score != null ? data.final_score : 0))
        trackText("fitScore", data.final_score != null ? String(data.final_score) : "0")
        trackText("mailStatus", data.mail_status)
        trackText("responseStatus", data.response_status)
        trackText("candidateEmail", data.email)
        trackText("candidatePhone", data.phone)
        trackText("candidateLocation", data.location)
        trackText("candidateExperience", data.experience !== "" ? data.experience + " years" : "-")
        trackText("jobTitle", data.job_title)
        trackText("companyName", data.company_name)
        trackText("candidateStatus", data.status)
        trackText("candidateDesignation", data.designation)
        trackText("candidateAvatar", candidateInitials(data.name))
        renderTimeline(data.timeline, data.current_stage)

        if(state) state.classList.add("hidden")
        if(content) content.classList.remove("hidden")
    }catch(err){
        if(state) state.innerText = "Could not load candidate tracking."
    }
}

loadCandidateTracking()
