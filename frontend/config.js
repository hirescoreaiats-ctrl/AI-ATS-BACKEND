// ===============================
// GLOBAL CONFIG FILE
// ===============================

// Backend API URL
const API = (() => {
    if(window.__HIRESCORE_API_BASE__){
        return String(window.__HIRESCORE_API_BASE__).replace(/\/$/, "");
    }

    const isLocalFrontend =
        window.location.protocol === "file:" ||
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1";

    return isLocalFrontend ? "http://127.0.0.1:8000" : window.location.origin;
})();


// ===============================
// AUTH HELPERS (OPTIONAL BUT BEST)
// ===============================

// Get token
function getToken(){
    return localStorage.getItem("token");
}

// Get auth headers
function getAuthHeaders(){
    return {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + getToken()
    };
}

const nativeFetch = window.fetch.bind(window);

window.fetch = function atsAuthenticatedFetch(input, init = {}) {
    const url = typeof input === "string" ? input : input?.url || "";
    const token = getToken();
    const isApiRequest = url.startsWith(API) || url.startsWith("/");

    if(!token || !isApiRequest){
        return nativeFetch(input, init);
    }

    const headers = new Headers(init.headers || {});
    if(!headers.has("Authorization")){
        headers.set("Authorization", "Bearer " + token);
    }

    return nativeFetch(input, {
        ...init,
        headers
    });
};


// ===============================
// DEBUG MODE (OPTIONAL)
// ===============================

const DEBUG = false;

function log(...args){
    if(!DEBUG) return;
}
