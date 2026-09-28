import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Flame, Clock, Ban, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { useAuthStore } from "@/store/authStore";
import {
  fetchWatchmanScore,
  submitWatchmanDecision,
  getWatchmanLabel,
  getWatchmanLabelDisplay,
} from "@/services/watchman";
import type { WatchmanDecision, WatchmanScoreData } from "@/types/watchman";
import type { ContentType } from "@/types/content";

interface WatchmanScoreCardProps {
  contentId: number;
  contentType: ContentType;
  initialScore?: number;
  initialLabel?: string;
  className?: string;
}

export function WatchmanScoreCard({
  contentId,
  contentType,
  initialScore,
  initialLabel,
  className = "",
}: WatchmanScoreCardProps) {
  const token = useAuthStore((state) => state.token);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const queryKey = ["watchman", contentType, contentId];

  // Fetch live score & user decision
  const { data: scoreData, isLoading } = useQuery<WatchmanScoreData>({
    queryKey,
    queryFn: () => fetchWatchmanScore(contentId, contentType),
    staleTime: 30_000,
  });

  // Active score calculation
  const score = scoreData?.final_score ?? (initialScore !== undefined ? initialScore : 50);
  const label: WatchmanDecision = scoreData?.watchman_label ?? getWatchmanLabel(score);
  const userDecision = scoreData?.user_decision ?? null;

  // SVG circular ring properties
  const radius = 42;
  const strokeWidth = 8;
  const circumference = 2 * Math.PI * radius;
  const progressPercent = Math.max(0, Math.min(100, score));
  const strokeDashoffset = circumference - (progressPercent / 100) * circumference;

  // Strict WatchMan color system (Gold/Yellow = positive, Neutral = time pass, Red = skip)
  const getThemeColor = (v: WatchmanDecision | string) => {
    switch (v) {
      case "must_watch":
        return {
          stroke: "#F5C518",
          text: "text-amber-400",
          glow: "drop-shadow(0 0 8px rgba(245, 197, 24, 0.45))",
          bg: "bg-amber-500/10",
          border: "border-amber-500/30",
          activeBg:
            "bg-amber-500/20 text-amber-300 border-amber-500 ring-2 ring-amber-500/30 shadow-[0_0_15px_rgba(245,197,24,0.25)]",
        };
      case "skip":
        return {
          stroke: "#EF4444",
          text: "text-red-500",
          glow: "drop-shadow(0 0 8px rgba(239, 68, 68, 0.45))",
          bg: "bg-red-500/10",
          border: "border-red-500/30",
          activeBg:
            "bg-red-500/20 text-red-400 border-red-500 ring-2 ring-red-500/30 shadow-[0_0_15px_rgba(239,68,68,0.25)]",
        };
      case "time_pass":
      default:
        return {
          stroke: "#9CA3AF",
          text: "text-neutral-300",
          glow: "none",
          bg: "bg-neutral-800/40",
          border: "border-neutral-700",
          activeBg:
            "bg-neutral-800 text-white border-neutral-400 ring-2 ring-neutral-400/20 shadow-md",
        };
    }
  };

  const currentTheme = getThemeColor(label);

  // Mutation with optimistic updates
  const decisionMutation = useMutation({
    mutationFn: (newDecision: WatchmanDecision) =>
      submitWatchmanDecision(contentId, newDecision, contentType),
    onMutate: async (newDecision) => {
      await queryClient.cancelQueries({ queryKey });
      const previousData = queryClient.getQueryData<WatchmanScoreData>(queryKey);

      if (previousData) {
        // Optimistically calculate new score and community counts
        let delta = 0;
        if (newDecision === "must_watch") delta = 12;
        else if (newDecision === "skip") delta = -18;

        const optimisticScore = Math.max(
          0,
          Math.min(100, Math.round(previousData.base_score + delta)),
        );
        const optimisticLabel = getWatchmanLabel(optimisticScore);

        const newCounts = { ...previousData.community_counts };
        if (previousData.user_decision && previousData.user_decision in newCounts) {
          newCounts[previousData.user_decision] = Math.max(
            0,
            newCounts[previousData.user_decision] - 1,
          );
        } else {
          newCounts.total += 1;
        }
        newCounts[newDecision] = (newCounts[newDecision] || 0) + 1;

        queryClient.setQueryData<WatchmanScoreData>(queryKey, {
          ...previousData,
          final_score: optimisticScore,
          watchman_label: optimisticLabel,
          label_display: getWatchmanLabelDisplay(optimisticLabel),
          user_decision: newDecision,
          community_counts: newCounts,
        });
      }

      return { previousData };
    },
    onError: (err, _newDecision, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKey, context.previousData);
      }
      toast.error("Failed to save verdict. Please try again.");
    },
    onSuccess: (updatedData) => {
      queryClient.setQueryData(queryKey, updatedData);
      toast.success(
        `Verdict recorded: ${getWatchmanLabelDisplay(updatedData.user_decision || "")}`,
      );
    },
  });

  const handleDecisionClick = (selectedDecision: WatchmanDecision) => {
    if (!token) {
      toast("Sign in to record your verdict", {
        description: "Join the community to vote and get personalized recommendations.",
        action: {
          label: "Sign In",
          onClick: () => navigate({ to: "/login" }),
        },
      });
      return;
    }

    decisionMutation.mutate(selectedDecision);
  };

  // Community breakdown math
  const community = scoreData?.community_counts;
  const totalVotes = community?.total || 0;
  const mustPct =
    totalVotes > 0 ? Math.round(((community?.must_watch || 0) / totalVotes) * 100) : 0;
  const timePct = totalVotes > 0 ? Math.round(((community?.time_pass || 0) / totalVotes) * 100) : 0;
  const skipPct = totalVotes > 0 ? Math.round(((community?.skip || 0) / totalVotes) * 100) : 0;

  return (
    <div
      className={`rounded-2xl border border-border/80 bg-card/80 backdrop-blur-md p-5 sm:p-6 shadow-xl ${className}`}
    >
      <div className="flex flex-col md:flex-row items-center justify-between gap-6">
        {/* Left: WatchMan Circular Score Ring */}
        <div className="flex items-center gap-5 shrink-0">
          <div className="relative flex items-center justify-center">
            <svg
              className="h-28 w-28 -rotate-90 transform"
              viewBox="0 0 100 100"
              aria-hidden="true"
            >
              {/* Background Track Ring */}
              <circle
                cx="50"
                cy="50"
                r={radius}
                className="stroke-neutral-800"
                strokeWidth={strokeWidth}
                fill="transparent"
              />
              {/* Dynamic Animated Value Ring */}
              <circle
                cx="50"
                cy="50"
                r={radius}
                stroke={currentTheme.stroke}
                strokeWidth={strokeWidth}
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                fill="transparent"
                style={{
                  filter: currentTheme.glow,
                  transition:
                    "stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1), stroke 0.4s ease",
                }}
              />
            </svg>

            {/* Inner Ring Score Display */}
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
              <span className="text-2xl font-black tracking-tight text-foreground">
                {Math.round(score)}%
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                WatchMan
              </span>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                WatchMan Verdict
              </span>
              {userDecision && (
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-primary">
                  <CheckCircle2 size={12} /> Your Vote
                </span>
              )}
            </div>
            <h3 className={`mt-0.5 text-2xl font-black tracking-tight ${currentTheme.text}`}>
              {getWatchmanLabelDisplay(label)}
            </h3>
            <p className="mt-1 max-w-xs text-xs text-muted-foreground leading-relaxed">
              {label === "must_watch" &&
                "High-priority essential viewing backed by critical and community consensus."}
              {label === "time_pass" &&
                "Casual, entertaining watch suitable for unwinding or background viewing."}
              {label === "skip" &&
                "Low-value viewing with mixed or unfavorable community feedback."}
            </p>
          </div>
        </div>

        {/* Right: Three Interactive Verdict Buttons */}
        <div className="w-full md:w-auto flex-1 flex flex-col items-center md:items-end gap-3">
          <div className="w-full max-w-md">
            <span className="block text-center md:text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              Your Verdict
            </span>
            <div className="grid grid-cols-3 gap-2 sm:gap-3">
              {/* MUST WATCH Button */}
              <button
                type="button"
                onClick={() => handleDecisionClick("must_watch")}
                disabled={decisionMutation.isPending}
                className={`flex flex-col sm:flex-row items-center justify-center gap-1.5 rounded-xl border py-2.5 px-3 text-xs font-bold transition-all duration-200 cursor-pointer ${
                  userDecision === "must_watch"
                    ? getThemeColor("must_watch").activeBg
                    : "border-border/80 bg-secondary/50 text-foreground hover:border-amber-500/60 hover:text-amber-400 hover:bg-amber-500/10"
                }`}
              >
                <Flame
                  size={15}
                  className={userDecision === "must_watch" ? "text-amber-400" : "text-amber-400/80"}
                />
                <span>MUST WATCH</span>
              </button>

              {/* TIME PASS Button */}
              <button
                type="button"
                onClick={() => handleDecisionClick("time_pass")}
                disabled={decisionMutation.isPending}
                className={`flex flex-col sm:flex-row items-center justify-center gap-1.5 rounded-xl border py-2.5 px-3 text-xs font-bold transition-all duration-200 cursor-pointer ${
                  userDecision === "time_pass"
                    ? getThemeColor("time_pass").activeBg
                    : "border-border/80 bg-secondary/50 text-foreground hover:border-neutral-500 hover:text-neutral-200 hover:bg-neutral-800/40"
                }`}
              >
                <Clock
                  size={15}
                  className={userDecision === "time_pass" ? "text-neutral-200" : "text-neutral-400"}
                />
                <span>TIME PASS</span>
              </button>

              {/* SKIP Button */}
              <button
                type="button"
                onClick={() => handleDecisionClick("skip")}
                disabled={decisionMutation.isPending}
                className={`flex flex-col sm:flex-row items-center justify-center gap-1.5 rounded-xl border py-2.5 px-3 text-xs font-bold transition-all duration-200 cursor-pointer ${
                  userDecision === "skip"
                    ? getThemeColor("skip").activeBg
                    : "border-border/80 bg-secondary/50 text-foreground hover:border-red-500/60 hover:text-red-400 hover:bg-red-500/10"
                }`}
              >
                <Ban
                  size={15}
                  className={userDecision === "skip" ? "text-red-400" : "text-red-400/80"}
                />
                <span>SKIP</span>
              </button>
            </div>
          </div>

          {/* Community Votes Bar */}
          <div className="w-full max-w-md pt-1">
            {totalVotes > 0 ? (
              <div className="space-y-1.5">
                <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-neutral-800">
                  <div
                    style={{ width: `${mustPct}%` }}
                    className="bg-amber-400 transition-all duration-500"
                    title={`Must Watch: ${mustPct}%`}
                  />
                  <div
                    style={{ width: `${timePct}%` }}
                    className="bg-neutral-400 transition-all duration-500"
                    title={`Time Pass: ${timePct}%`}
                  />
                  <div
                    style={{ width: `${skipPct}%` }}
                    className="bg-red-500 transition-all duration-500"
                    title={`Skip: ${skipPct}%`}
                  />
                </div>
                <div className="flex justify-between items-center text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400" /> {mustPct}% Must
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-neutral-400" /> {timePct}% Pass
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-red-500" /> {skipPct}% Skip
                  </span>
                  <span className="font-semibold text-foreground/80">
                    ({totalVotes.toLocaleString()} votes)
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-center md:text-right text-[11px] text-muted-foreground">
                No community votes yet. Be the first to vote!
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
