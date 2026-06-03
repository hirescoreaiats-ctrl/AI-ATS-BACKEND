(function(){
var API = (function(){
if(window.__HIRESCORE_API_BASE__){
return String(window.__HIRESCORE_API_BASE__).replace(/\/$/, "")
}
var isLocalFrontend =
window.location.protocol === "file:" ||
window.location.hostname === "localhost" ||
window.location.hostname === "127.0.0.1"
return isLocalFrontend ? "http://127.0.0.1:8000" : window.location.origin
})()
var params = new URLSearchParams(window.location.search)
var jobId = params.get("job_id")
var applicationSource = normalizeSource(params.get("source"))
var applyTrackingUrl = window.location.href
var resumeAutofillToken = 0

var els = {}

function bindElements(){
els = {
brandMark: document.getElementById("brandMark"),
brandCompany: document.getElementById("brandCompany"),
jobTitle: document.getElementById("jobTitle"),
company: document.getElementById("company"),
location: document.getElementById("location"),
salary: document.getElementById("salary"),
jobType: document.getElementById("jobType"),
experience: document.getElementById("experience"),
workMode: document.getElementById("workMode"),
description: document.getElementById("description"),
form: document.getElementById("applyForm"),
file: document.getElementById("resumeFile"),
fileName: document.getElementById("fileName"),
uploadZone: document.getElementById("uploadZone"),
progressBox: document.getElementById("uploadProgressBox"),
progressBar: document.getElementById("uploadProgressBar"),
uploadPercent: document.getElementById("uploadPercent"),
submitBtn: document.getElementById("submitBtn"),
message: document.getElementById("formMessage")
}
}

function text(value, fallback="Not specified"){
return String(value || "").trim() || fallback
}

function initials(value){
return text(value, "AI").split(/\s+/).slice(0,2).map(part => part[0]).join("").toUpperCase()
}

function normalizeSource(source){
let value = String(source || "").trim().toLowerCase()
let allowed = ["linkedin","whatsapp","naukri","referral","website","direct","unknown"]
if(!value) return "direct"
return allowed.includes(value) ? value : "unknown"
}

function setMessage(type, message){
els.message.className = "message " + type
els.message.textContent = message
}

function clearMessage(){
els.message.className = "message"
els.message.textContent = ""
}

function fillIfBlank(id, value){
let element = document.getElementById(id)
let textValue = String(value || "").trim()
if(element && textValue && !String(element.value || "").trim()){
element.value = textValue
}
}

async function autofillFromResume(file){
let token = ++resumeAutofillToken
let formData = new FormData()
formData.append("file", file)

setMessage("success", "Reading resume and filling candidate details...")

try{
let res = await fetch(`${API}/parse-resume-autofill`, {
method: "POST",
body: formData
})
let data = await res.json().catch(() => ({}))

if(token !== resumeAutofillToken) return
if(!res.ok){
throw new Error(data.detail || "Could not read candidate details from this resume.")
}

let fields = data.fields || {}
fillIfBlank("fullName", fields.form_full_name)
fillIfBlank("email", fields.form_email)
fillIfBlank("phone", fields.form_phone)
fillIfBlank("candidateLocation", fields.form_location)
fillIfBlank("linkedin", fields.linkedin)
setMessage("success", "Resume details filled. Please review before submitting.")
}
catch(error){
if(token !== resumeAutofillToken) return
setMessage("error", error.message || "Resume details could not be auto-filled. You can fill the form manually.")
}
}

function escapeHtml(value){
return String(value)
.replace(/&/g,"&amp;")
.replace(/</g,"&lt;")
.replace(/>/g,"&gt;")
.replace(/"/g,"&quot;")
.replace(/'/g,"&#039;")
}

function formatDescription(description){
let raw = text(description, "No detailed job description has been added yet.")
let lines = raw.split(/\r?\n/).map(line => line.trim()).filter(Boolean)

if(!lines.length){
return "<p>No detailed job description has been added yet.</p>"
}

let html = ""
let listOpen = false
let sectionListMode = false

lines.forEach(line => {
let heading = /^(job summary|summary|responsibilities|requirements|skills|required skills|preferred skills|qualification|qualifications|experience|salary|about the role|benefits)[:]?$/i.test(line)
let bullet = /^[-*]/.test(line) || /^[0-9]+[.)]\s+/.test(line)
let listHeading = /^(responsibilities|requirements|skills|required skills|preferred skills|qualification|qualifications|benefits)[:]?$/i.test(line)

if(heading){
if(listOpen){
html += "</ul>"
listOpen = false
}
sectionListMode = listHeading
html += `<strong>${escapeHtml(line.replace(/:$/,""))}</strong>`
return
}

if(bullet || sectionListMode){
if(!listOpen){
html += "<ul>"
listOpen = true
}
let cleanBullet = line.replace(/^[-*]\s*/,"").replace(/^[0-9]+[.)]\s+/,"")
html += `<li>${escapeHtml(cleanBullet)}</li>`
return
}

if(listOpen){
html += "</ul>"
listOpen = false
}
html += `<p>${escapeHtml(line)}</p>`
})

if(listOpen){
html += "</ul>"
}

return html
}

async function loadJob(){
if(!jobId){
els.jobTitle.textContent = "Job link is missing"
els.description.innerHTML = "<p>This application link does not include a job id.</p>"
return
}

try{
let res = await fetch(`${API}/public-job/${encodeURIComponent(jobId)}`)
let job = await res.json()

if(job.error){
throw new Error(job.error)
}

document.title = `Apply for ${text(job.job_title, "Job")}`
els.jobTitle.textContent = text(job.job_title, "Open Role")
els.company.textContent = text(job.company, "Company")
els.brandCompany.textContent = text(job.company, "HireScore AI Careers")
els.brandMark.textContent = initials(job.company)
els.location.textContent = text(job.location)
els.salary.textContent = text(job.salary, "Not disclosed")
els.jobType.textContent = text(job.job_type)
els.experience.textContent = text(job.experience_required, "Role dependent")
els.workMode.textContent = text(job.work_mode, "Screening ready")
els.description.innerHTML = formatDescription(job.description)
}
catch(error){
els.jobTitle.textContent = "Job not available"
els.description.innerHTML = `<p>${escapeHtml(error.message || "Could not load this job right now.")}</p>`
}
}

function bindUpload(){
els.file.addEventListener("change", () => {
let file = els.file.files && els.file.files[0]
els.fileName.textContent = file ? file.name : "No file selected"
if(file){
autofillFromResume(file)
}else{
++resumeAutofillToken
}
})

;["dragenter","dragover"].forEach(eventName => {
els.uploadZone.addEventListener(eventName, event => {
event.preventDefault()
els.uploadZone.classList.add("is-dragging")
})
})

;["dragleave","drop"].forEach(eventName => {
els.uploadZone.addEventListener(eventName, event => {
event.preventDefault()
els.uploadZone.classList.remove("is-dragging")
})
})
}

function bindSubmit(){
els.form.addEventListener("submit", function(event){
event.preventDefault()
clearMessage()

if(!jobId){
setMessage("error", "This application link is missing a job id.")
return
}

if(!els.file.files.length){
setMessage("error", "Please upload your resume before submitting.")
return
}

const formData = new FormData(els.form)
formData.set("application_source", applicationSource)
formData.set("apply_tracking_url", applyTrackingUrl)
const xhr = new XMLHttpRequest()

xhr.open("POST", `${API}/public-upload-resumes/${encodeURIComponent(jobId)}`)
els.progressBox.style.display = "block"
els.progressBar.style.width = "0%"
els.uploadPercent.textContent = "0%"
els.submitBtn.disabled = true
els.submitBtn.textContent = "Submitting..."

xhr.upload.onprogress = function(progressEvent){
if(progressEvent.lengthComputable){
let percent = Math.round((progressEvent.loaded / progressEvent.total) * 100)
els.progressBar.style.width = percent + "%"
els.uploadPercent.textContent = percent + "%"
}
}

xhr.onload = function(){
els.submitBtn.disabled = false
els.submitBtn.textContent = "Submit Application"

let data = {}
try{
data = JSON.parse(xhr.responseText || "{}")
}catch(err){
data = {}
}

if(xhr.status >= 200 && xhr.status < 300){
if(!data.total_resumes || Number(data.total_resumes) < 1){
setMessage("error", data.detail || "Application reached the server, but no resume was saved. Please upload a PDF or DOCX resume and try again.")
return
}
els.progressBar.style.width = "100%"
els.uploadPercent.textContent = "100%"
setMessage("success", data.processing ? "Application submitted. AI screening is running in the background." : "Application submitted successfully. The recruiting team can now review your profile.")
els.form.reset()
els.fileName.textContent = "No file selected"
return
}

setMessage("error", data.detail || "Application could not be submitted. Please check your file and try again.")
}

xhr.onerror = function(){
els.submitBtn.disabled = false
els.submitBtn.textContent = "Submit Application"
setMessage("error", "Network error while submitting the application. Please try again.")
}

xhr.send(formData)
})
}

function init(){
bindElements()
bindUpload()
bindSubmit()
loadJob()
}

if(document.readyState === "loading"){
document.addEventListener("DOMContentLoaded", init)
}else{
init()
}
})()
