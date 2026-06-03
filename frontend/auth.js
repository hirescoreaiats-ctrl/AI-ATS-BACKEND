


// ---------------- SIGNUP ----------------

let paidAccessConfig = {
checkoutUrl: "",
salesEmail: "sales@example.com"
}

function savePendingSignupContext(data){
let detail = data?.detail || {}
if(typeof detail !== "object" || !detail.pending_signup_token) return ""
sessionStorage.setItem("pendingSignupToken", detail.pending_signup_token)
sessionStorage.setItem("pendingSignupEmail", detail.email || "")
sessionStorage.setItem("pendingSignupName", detail.name || "")
return detail.pending_signup_token
}

function showAuthError(message){
let errorBox = document.getElementById("error")
if(errorBox){
errorBox.innerText = message
errorBox.classList.remove("hidden")
}else{
alert(message)
}
}

function showOAuthErrorFromUrl(){
let params = new URLSearchParams(window.location.search)
let error = params.get("error")
if(!error) return

let messages = {
google_not_configured: "Google sign-in is not configured yet. Please sign in with email/password or ask admin to configure Google OAuth.",
google_auth_failed: "Google sign-in could not be completed. Please try again or use email/password login.",
google_account_not_found: "No account exists for this Google email. Please create an account first.",
gmail_email_mismatch: "Please connect the same Google Mail account entered as the outreach sender."
,
paid_access_required: "Paid access required. Complete checkout or enter a valid invite/access code."
}

showAuthError(messages[error] || "Authentication failed. Please try again.")
window.history.replaceState({}, document.title, window.location.pathname)
}

async function refreshAuthProviders(){
let googleBtn = document.getElementById("googleBtn")

try{
let res = await fetch(API + "/auth-providers")
let data = await res.json()

if(googleBtn){
if(!data.google_enabled){
googleBtn.dataset.enabled = "false"
googleBtn.classList.remove("auth-google-disabled")
googleBtn.title = "Continue with Google"
}
else{
googleBtn.dataset.enabled = "true"
googleBtn.classList.remove("auth-google-disabled")
googleBtn.title = "Continue with Google"
}
}

let paidNotice = document.getElementById("paidSignupNotice")
let checkoutBtn = document.getElementById("checkoutBtn")
paidAccessConfig.checkoutUrl = data.checkout_url || ""
paidAccessConfig.salesEmail = data.sales_contact_email || "sales@example.com"
if(paidNotice){
paidNotice.classList.toggle("hidden", !data.paid_signup_required)
}
if(checkoutBtn){
checkoutBtn.classList.toggle("hidden", !data.paid_signup_required)
checkoutBtn.innerText = "View Plans & Buy Access"
checkoutBtn.onclick = () => startPaidSignup()
}
}catch(err){
if(googleBtn){
googleBtn.dataset.enabled = "false"
googleBtn.classList.remove("auth-google-disabled")
googleBtn.title = "Continue with Google"
}
}
}

document.addEventListener("DOMContentLoaded", () => {
completeOAuthLogin()
showOAuthErrorFromUrl()
if(document.getElementById("googleBtn") || document.getElementById("checkoutBtn") || document.getElementById("paidSignupNotice")){
refreshAuthProviders()
}
})

function openPricingPage(){
let email = document.getElementById("email")?.value || sessionStorage.getItem("pendingSignupEmail") || ""
let token = sessionStorage.getItem("pendingSignupToken") || ""
let params = new URLSearchParams()
if(email) params.set("email", email)
if(token) params.set("pending_signup_token", token)
let suffix = params.toString() ? "?" + params.toString() : ""
window.location.href = "pricing.html" + suffix
}

function startPaidSignup(){
let name = document.getElementById("name")?.value || ""
let email = document.getElementById("email")?.value || ""
let password = document.getElementById("password")?.value || ""
if(name && email && password){
signupUser()
return
}
openPricingPage()
}

function choosePaidPlan(plan){
let params = new URLSearchParams(window.location.search)
let email = document.getElementById("email")?.value || params.get("email") || sessionStorage.getItem("pendingSignupEmail") || ""
let pendingToken = params.get("pending_signup_token") || sessionStorage.getItem("pendingSignupToken") || ""
let planLabels = {
starter: "Starter",
"agency-pro": "Agency Pro",
enterprise: "Enterprise"
}
let label = planLabels[plan] || plan

if(paidAccessConfig.checkoutUrl){
let separator = paidAccessConfig.checkoutUrl.includes("?") ? "&" : "?"
let successUrl = pendingToken
? `${API}/paid-signup-complete?pending_signup_token=${encodeURIComponent(pendingToken)}&plan=${encodeURIComponent(plan)}`
: ""
window.location.href = `${paidAccessConfig.checkoutUrl}${separator}plan=${encodeURIComponent(plan)}&email=${encodeURIComponent(email)}&success_url=${encodeURIComponent(successUrl)}`
return
}

window.location.href = `mailto:${paidAccessConfig.salesEmail}?subject=HireScore AI ${encodeURIComponent(label)} plan access&body=Hi, I want paid access for HireScore AI.%0APlan: ${encodeURIComponent(label)}%0AEmail: ${encodeURIComponent(email)}`
}

async function signupUser(){

let name = document.getElementById("name").value
let email = document.getElementById("email").value
let password = document.getElementById("password").value
let accessCode = document.getElementById("accessCode")?.value || ""
let errorBox = document.getElementById("error")

if(errorBox) errorBox.classList.add("hidden")

if(!name || !email || !password){
if(errorBox){
errorBox.innerText = "All fields required"
errorBox.classList.remove("hidden")
}else{
alert("All fields required")
}
return
}

try{

let res = await fetch(API + "/signup",{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({
name:name,
email:email,
password:password,
access_code:accessCode
})
})

let data = await res.json()

if(data.message){
alert("Account Created OK")
window.location.href = "login.html"
}else{
if(res.status === 402){
savePendingSignupContext(data)
openPricingPage()
return
}
if(errorBox){
errorBox.innerText = data.detail || "Signup failed"
errorBox.classList.remove("hidden")
}else{
alert(data.detail)
}
}

}catch(err){
alert("Server error")
}

}


// ---------------- LOGIN ----------------

async function loginUser(){

let email = document.getElementById("email").value
let password = document.getElementById("password").value
let errorBox = document.getElementById("error")
let btn = document.getElementById("loginBtn")

if(errorBox) errorBox.classList.add("hidden")

if(!email || !password){
if(errorBox){
errorBox.innerText = "Enter email & password"
errorBox.classList.remove("hidden")
}else{
alert("Enter email & password")
}
return
}

// loading loader
if(btn){
btn.innerText = "Logging in..."
btn.disabled = true
}

try{

let res = await fetch(API + "/login",{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({
email:email,
password:password
})
})

let data = await res.json()

if(data.token){

localStorage.setItem("token", data.token)
localStorage.setItem("username", data.name)
localStorage.setItem("userEmail", data.email || email)

// redirect redirect
window.location.href = "index.html"

}else{
if(errorBox){
errorBox.innerText = data.detail || "Login failed"
errorBox.classList.remove("hidden")
}else{
alert(data.detail)
}
}

}catch(err){
if(errorBox){
errorBox.innerText = "Server error"
errorBox.classList.remove("hidden")
}else{
alert("Server error")
}
}

// loading reset button
if(btn){
btn.innerText = "Login"
btn.disabled = false
}

}


// ---------------- GOOGLE LOGIN ----------------

function googleLogin(){
let page = window.location.pathname.toLowerCase()
let mode = page.includes("signup") ? "signup" : "login"
let accessCode = document.getElementById("accessCode")?.value || ""
window.location.href = API + "/google-login?mode=" + encodeURIComponent(mode) + "&access_code=" + encodeURIComponent(accessCode)
}


// ---------------- SESSION HELPERS ----------------

function getFrontendPage(fileName){
let path = window.location.pathname
let base = path.substring(0, path.lastIndexOf("/") + 1)
return base + fileName
}

function parseJwt(token){
try{
let payload = token.split(".")[1]
let json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"))
return JSON.parse(decodeURIComponent(json.split("").map(c =>
"%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)
).join("")))
}catch(err){
return null
}
}

function isTokenExpired(token){
let payload = parseJwt(token)
if(!payload || !payload.exp) return false
return Date.now() >= payload.exp * 1000
}

function completeOAuthLogin(){
let params = new URLSearchParams(window.location.search)
let token = params.get("token")
let name = params.get("name")
let email = params.get("email")
let gmailConnected = params.get("gmail_connected")

if(token){
localStorage.setItem("token", token)
let payload = parseJwt(token) || {}
if(name) localStorage.setItem("username", decodeURIComponent(name))
else if(payload.name) localStorage.setItem("username", payload.name)
if(email) localStorage.setItem("userEmail", decodeURIComponent(email))
else if(payload.email) localStorage.setItem("userEmail", payload.email)
window.history.replaceState({}, document.title, window.location.pathname)
}

if(gmailConnected){
localStorage.setItem("gmailConnected", "true")
if(email){
localStorage.setItem("outreachSenderEmail", decodeURIComponent(email))
localStorage.setItem("gmailConnectedEmail", decodeURIComponent(email))
}
window.history.replaceState({}, document.title, window.location.pathname)
}
}

// ---------------- LOGOUT ----------------

function logoutUser(){
localStorage.removeItem("token")
localStorage.removeItem("username")
localStorage.removeItem("userEmail")
localStorage.removeItem("outreachSenderEmail")
localStorage.removeItem("gmailConnected")
localStorage.removeItem("gmailConnectedEmail")
window.location.href = getFrontendPage("login.html")
}


// ---------------- CHECK LOGIN ----------------

function checkLogin(){
completeOAuthLogin()

let token = localStorage.getItem("token")

if(!token || isTokenExpired(token)){
localStorage.removeItem("token")
localStorage.removeItem("username")
window.location.href = getFrontendPage("login.html")
return
}

let name = localStorage.getItem("username") || "Recruiter"

let profile = document.getElementById("profileName")

if(profile){
profile.innerText = name
}
}


// ---------------- RESET PASSWORD ----------------

async function resetPassword(){
let email = document.getElementById("email")?.value?.trim()
let btn = event?.target

if(!email){
showAuthError("Enter your registered email")
return
}

if(btn){
btn.innerText = "Resetting..."
btn.disabled = true
}

try{
let res = await fetch(API + "/reset-password", {
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({email})
})

let data = await res.json()

if(!res.ok){
showAuthError(data.detail || "Password reset failed")
return
}

let messageBox = document.getElementById("resetMessage")
let message = data.mail_sent
? "Password reset email sent. Please check your inbox."
: "Password reset successfully. Temporary password: " + data.temporary_password

if(messageBox){
messageBox.innerText = message
messageBox.classList.remove("hidden")
}else{
alert(message)
}
}catch(err){
showAuthError("Server error. Please try again.")
}finally{
if(btn){
btn.innerText = "Reset Password"
btn.disabled = false
}
}
}
