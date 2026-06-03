import { AnalyticsRoute } from "./AnalyticsRoute.jsx";
import { CandidatesRoute } from "./CandidatesRoute.jsx";
import { CopilotRoute } from "./CopilotRoute.jsx";
import { InboxRoute } from "./InboxRoute.jsx";
import { InterviewsRoute } from "./InterviewsRoute.jsx";
import { OrganizationRoute } from "./OrganizationRoute.jsx";
import { PipelineRoute } from "./PipelineRoute.jsx";
import { TalentRoute } from "./TalentRoute.jsx";

export const routes = {
  "/pipeline": PipelineRoute,
  "/candidates": CandidatesRoute,
  "/talent": TalentRoute,
  "/inbox": InboxRoute,
  "/copilot": CopilotRoute,
  "/analytics": AnalyticsRoute,
  "/interviews": InterviewsRoute,
  "/organization": OrganizationRoute,
  "/jobs": PipelineRoute,
  "/settings": OrganizationRoute
};

export function resolveRoute(pathname) {
  return routes[pathname] || PipelineRoute;
}
