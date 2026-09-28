export type WatchmanDecision = "must_watch" | "time_pass" | "skip";

export interface WatchmanCommunityCounts {
  must_watch: number;
  time_pass: number;
  skip: number;
  total: number;
}

export interface WatchmanScoreData {
  content_id: number;
  content_type: string;
  base_score: number;
  final_score: number;
  watchman_label: WatchmanDecision;
  label_display: string;
  user_decision: WatchmanDecision | null;
  community_counts: WatchmanCommunityCounts;
}
