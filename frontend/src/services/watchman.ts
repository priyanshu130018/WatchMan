import { api } from "@/lib/api";
import type { WatchmanDecision, WatchmanScoreData } from "@/types/watchman";

/**
 * Classify a 0-100 score into WatchMan verdict categories.
 * 75-100: must_watch
 * 45-74:  time_pass
 * 0-44:   skip
 */
export function getWatchmanLabel(score: number): WatchmanDecision {
  if (score >= 75) return "must_watch";
  if (score >= 45) return "time_pass";
  return "skip";
}

/**
 * Formats a WatchMan verdict into clean user-facing label text.
 */
export function getWatchmanLabelDisplay(label: WatchmanDecision | string): string {
  switch (label) {
    case "must_watch":
      return "MUST WATCH";
    case "time_pass":
      return "TIME PASS";
    case "skip":
      return "SKIP";
    default:
      return "TIME PASS";
  }
}

/**
 * Fetch dynamic WatchMan score, verdict, community breakdown, and user decision.
 */
export async function fetchWatchmanScore(
  contentId: number,
  contentType?: string,
): Promise<WatchmanScoreData> {
  const resp = await api.get(`/content/${contentId}/watchman`, {
    params: contentType ? { content_type: contentType } : undefined,
  });
  return resp.data.data;
}

/**
 * Submit or update user decision (must_watch, time_pass, skip) for content.
 */
export async function submitWatchmanDecision(
  contentId: number,
  decision: WatchmanDecision,
  contentType: string = "movie",
): Promise<WatchmanScoreData> {
  const resp = await api.put(`/content/${contentId}/watchman`, {
    decision,
    content_type: contentType,
  });
  return resp.data.data;
}
