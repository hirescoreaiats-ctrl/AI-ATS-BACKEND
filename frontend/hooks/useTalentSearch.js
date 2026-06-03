import { useMemo } from "react";
import { demoCandidates } from "../lib/demoData.js";
import { enterpriseApi } from "../services/enterpriseApi.js";
import { useAsyncResource } from "./useAsyncResource.js";
import { useDebouncedValue } from "./useDebouncedValue.js";

export function useTalentSearch({ query, stage }) {
  const debouncedQuery = useDebouncedValue(query, 280);
  const fallback = useMemo(() => ({ results: demoCandidates, total: demoCandidates.length }), []);

  return useAsyncResource(
    async () => {
      try {
        return await enterpriseApi.searchCandidates({ q: debouncedQuery, stage });
      } catch {
        return fallback;
      }
    },
    [debouncedQuery, stage],
    fallback
  );
}
