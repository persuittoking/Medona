import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { Subject, Summary } from "../api/types";
import { useAuth } from "./auth";

const SUBJECTS: Subject[] = ["pregnancy", "child", "all"];

function storageKey(userId: number | undefined): string {
  return `onaradar.subject.${userId ?? "anon"}`;
}

function read(key: string): Subject {
  try {
    const v = localStorage.getItem(key);
    return SUBJECTS.includes(v as Subject) ? (v as Subject) : "pregnancy";
  } catch {
    return "pregnancy";
  }
}

/** The "Homiladorlar | Bolalar | Hammasi" choice, remembered per user (localStorage). Default: pregnancies. */
export function useSubject(): [Subject, (s: Subject) => void] {
  const { user } = useAuth();
  const key = storageKey(user?.id);
  const [state, setState] = useState<{ key: string; value: Subject }>(() => ({ key, value: read(key) }));
  const value = state.key === key ? state.value : read(key);
  const set = useCallback((s: Subject) => {
    setState({ key, value: s });
    try {
      localStorage.setItem(key, s);
    } catch {
      /* storage unavailable: the choice lasts for this page only */
    }
  }, [key]);
  return [value, set];
}

export const showsPregnancies = (s: Subject) => s !== "child";
export const showsChildren = (s: Subject) => s !== "pregnancy";

/** Counts for the switch segments on staff screens (from the dashboard summary; tenant-scoped). */
export function useStaffSubjectCounts() {
  return useQuery({
    queryKey: ["summary", "pregnancy"],
    queryFn: () => api<Summary>("/api/dashboard/summary?subject=pregnancy"),
    refetchInterval: 30000,
  }).data?.counts;
}
