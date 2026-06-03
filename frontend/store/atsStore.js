import { create } from "zustand";

export const useATSStore = create((set) => ({
  selectedJobId: null,
  search: "",
  stageFilter: "all",
  selectedCandidate: null,
  setSelectedJobId: (selectedJobId) => set({ selectedJobId }),
  setSearch: (search) => set({ search }),
  setStageFilter: (stageFilter) => set({ stageFilter }),
  setSelectedCandidate: (selectedCandidate) => set({ selectedCandidate })
}));
