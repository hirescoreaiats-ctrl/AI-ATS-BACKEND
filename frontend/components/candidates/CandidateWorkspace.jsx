import { useState } from "react";
import { enterpriseApi } from "../../services/enterpriseApi.js";
import { useAsyncResource } from "../../hooks/useAsyncResource.js";
import { ATSDataTable } from "../tables/ATSDataTable.jsx";
import { CandidateProfileDrawer } from "./CandidateProfileDrawer.jsx";

export function CandidateWorkspace({ candidates = [] }) {
  const [selected, setSelected] = useState(null);
  const { data: timeline } = useAsyncResource(
    async () => {
      if (!selected) return null;
      const [base, stageHistory] = await Promise.all([
        enterpriseApi.candidateTimeline(selected.resume_id || selected.id),
        enterpriseApi.candidateStageHistory(selected.resume_id || selected.id)
      ]);
      return { ...base, history: stageHistory.history };
    },
    [selected?.resume_id, selected?.id],
    null
  );

  return (
    <>
      <ATSDataTable rows={candidates} onRowClick={setSelected} />
      <CandidateProfileDrawer candidate={selected} open={Boolean(selected)} onClose={() => setSelected(null)} timeline={timeline} />
    </>
  );
}
