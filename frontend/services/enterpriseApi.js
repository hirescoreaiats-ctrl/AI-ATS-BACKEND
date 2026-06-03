import { apiGet, apiPost } from "./apiClient.js";

export const enterpriseApi = {
  searchCandidates: ({ q = "", stage = "all", page = 1, pageSize = 25 }) =>
    apiGet(`/api/v1/talent/search?q=${encodeURIComponent(q)}&stage=${encodeURIComponent(stage)}&page=${page}&page_size=${pageSize}`),
  candidateTimeline: (candidateId) => apiGet(`/api/v1/enterprise/candidates/${candidateId}/timeline`),
  candidateStageHistory: (candidateId) => apiGet(`/api/v1/enterprise/candidates/${candidateId}/stage-history`),
  similarCandidates: (candidateId) => apiGet(`/api/v1/ai/candidates/${candidateId}/similar`),
  moveCandidate: (payload) => apiPost("/api/v1/enterprise/pipeline/move", payload),
  bulkMoveCandidates: (payload) => apiPost("/api/v1/enterprise/pipeline/bulk-move", payload),
  copilotChat: (payload) => apiPost("/api/v1/copilot/chat", payload),
  compareCandidates: (payload) => apiPost("/api/v1/copilot/compare", payload),
  interviewPrep: (candidateId) => apiGet(`/api/v1/copilot/candidates/${candidateId}/interview-prep`),
  createOffer: (payload) => apiPost("/api/v1/enterprise/offers", payload),
  schedulePanel: (payload) => apiPost("/api/v1/interviews/panel", payload),
  createInterviewKit: (payload) => apiPost("/api/v1/interviews/kits", payload),
  organizations: () => apiGet("/api/v1/organizations")
};
