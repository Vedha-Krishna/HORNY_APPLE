import { useEffect, useMemo, useState } from "react";
import { create } from "zustand";
import { supabase } from "../../lib/supabase";
import {
  mockIncidents,
  mockClusters,
  SG_CENTER,
  type Incident,
  type Cluster,
  type Severity,
  type AgentLog,
  type AgentMessage,
} from "./mockData";

// Fallback area-center lookup when DB coordinates are missing or imprecise.
const SG_COORDS: Record<string, [number, number]> = {
  "ang mo kio":    [1.3691, 103.8454],
  "bedok":         [1.3236, 103.9273],
  "bishan":        [1.3526, 103.8352],
  "boon lay":      [1.3404, 103.7090],
  "bugis":         [1.3009, 103.8555],
  "bukit batok":   [1.3490, 103.7495],
  "bukit timah":   [1.3294, 103.8021],
  "changi":        [1.3644, 103.9915],
  "chinatown":     [1.2836, 103.8444],
  "choa chu kang": [1.3840, 103.7470],
  "clementi":      [1.3162, 103.7649],
  "dhoby ghaut":   [1.2990, 103.8456],
  "harbourfront":  [1.2650, 103.8198],
  "hougang":       [1.3613, 103.8863],
  "jurong east":   [1.3331, 103.7420],
  "kallang":       [1.3119, 103.8631],
  "little india":  [1.3066, 103.8518],
  "orchard":       [1.3048, 103.8318],
  "pasir ris":     [1.3730, 103.9494],
  "punggol":       [1.3984, 103.9072],
  "queenstown":    [1.2942, 103.8060],
  "sengkang":      [1.3868, 103.8914],
  "serangoon":     [1.3554, 103.8679],
  "tampines":      [1.3530, 103.9450],
  "tanjong pagar": [1.2764, 103.8446],
  "toa payoh":     [1.3343, 103.8563],
  "woodlands":     [1.4382, 103.7891],
  "yishun":        [1.4295, 103.8350],
};

export function getAreaCenter(locationText: string | null): [number, number] | null {
  if (!locationText) return null;
  const lower = locationText.toLowerCase();
  for (const [name, coords] of Object.entries(SG_COORDS)) {
    if (lower.includes(name)) return coords;
  }
  return null;
}

function isValidNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isSingaporeCoordinate(lat: number, lng: number): boolean {
  // Covers Singapore and nearby islands.
  return lat >= 1.16 && lat <= 1.48 && lng >= 103.6 && lng <= 104.1;
}

// Category mapping
function normalizeCategory(cat: string | null): string {
  return (cat ?? "uncategorized")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "uncategorized";
}

function mapCategory(cat: string | null): string {
  const normalized = normalizeCategory(cat);

  switch (normalized) {
    case "theft":
    case "attempted_theft":   return "theft";
    case "vandalism":         return "vandalism";
    case "robbery":           return "snatch_theft";
    case "scam_fraud":        return "scam";
    case "harassment_threat":
    case "assault":
    case "sexual_offense":
    case "harassment":      return "harassment";
    default:                return normalized;
  }
}

// Numeric severity score → display enum
function mapSeverity(score: number | null): Severity {
  if (score === null) return "medium";
  if (score >= 0.7)   return "critical";
  if (score >= 0.5)   return "high";
  if (score >= 0.3)   return "medium";
  return "low";
}

// DB row shape returned by the incident_full view.
// Fields come from multiple tables pre-joined by the view.
interface DbRow {
  // incidents (core)
  incident_id:        string;
  source_platform:    string | null;
  source_url?:        string | null;
  raw_text:           string | null;
  timestamp_text:     string | null;
  normalized_time:    string | null;
  created_at:         string | null;
  // incident_queue
  status:             string | null;
  // incident_analysis
  cleaned_content:    string | null;
  category:           string | null;
  authenticity_score: number | null;
  severity:           number | null;
  // incident_locations
  location_text:      string | null;
  latitude:           number | null;
  longitude:          number | null;
  // incident_decisions
  decision?:          string | null;
  decision_reason?:   string | null;
  // incident_agent_messages aggregated as JSONB array by the view
  agent_messages?:    unknown[] | null;
}

function validIsoTimestamp(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  return Number.isNaN(new Date(trimmed).getTime()) ? null : trimmed;
}

function normalizeLocationText(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  return trimmed;
}

function isGenericLocationText(value: string): boolean {
  const normalized = value.toLowerCase().replace(/\s+/g, " ").trim();
  return (
    normalized === "singapore" ||
    normalized === "sg" ||
    normalized === "no location" ||
    normalized === "unknown" ||
    normalized === "n/a" ||
    normalized === "na"
  );
}

function rowToIncident(r: DbRow): Incident {
  const locationText = normalizeLocationText(r.location_text);
  const hasSpecificLocationText =
    locationText !== null && !isGenericLocationText(locationText);

  // Only trust coordinates that fall inside Singapore's bounding box.
  const dbCoords =
    isValidNumber(r.latitude) &&
    isValidNumber(r.longitude) &&
    isSingaporeCoordinate(r.latitude, r.longitude)
      ? ([r.latitude, r.longitude] as [number, number])
      : null;
  const inferredCoords = hasSpecificLocationText
    ? getAreaCenter(locationText)
    : null;
  // Guardrail: if location text is missing/generic, do not show map pins even if
  // stale/default coordinates exist in DB.
  const hasMapLocation =
    hasSpecificLocationText && (dbCoords !== null || inferredCoords !== null);
  // Prefer the name-matched coords — they align better with the displayed area label
  // than raw DB coordinates which can be stale or too generic.
  const [lat, lng] = hasMapLocation
    ? (inferredCoords ?? dbCoords ?? SG_CENTER)
    : SG_CENTER;
  const area = hasMapLocation ? locationText! : "No location";
  const confidence = r.authenticity_score ?? 0.5;
  const description = r.cleaned_content || r.raw_text || "";
  const categoryLabel = r.category
    ? r.category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : "Incident";
  const postCreatedAt =
    validIsoTimestamp(r.timestamp_text) ?? validIsoTimestamp(r.normalized_time);

  return {
    id:       r.incident_id,
    type:     mapCategory(r.category),
    severity: mapSeverity(r.severity),
    title:    categoryLabel,
    description,
    location: { area, lat, lng },
    hasMapLocation,
    source: r.source_platform ?? "unknown",
    source_url: r.source_url ?? null,
    verified: r.cleaned_content !== null,
    confidence,
    timestamp: postCreatedAt ?? "",
    cluster_id: null,
  };
}

function mapDecisionToAgentDecision(decision?: string | null, status?: string | null): AgentLog["decision"] {
  // status='processed' is the authoritative signal that the incident was approved,
  // even when the decision field is null (e.g. pre-migration data).
  if (status === "processed") return "ACCEPTED";
  if (!decision) return "REJECTED";
  const normalized = decision.toLowerCase();
  if (normalized === "publish" || normalized === "accepted" || normalized === "processed") return "ACCEPTED";
  return "REJECTED";
}

const OVERSEAS_DECISION_REASON =
  "This report describes an incident outside Singapore and does not create a direct public-safety risk in Singapore. Overseas incidents are rejected for the Singapore petty-crime pipeline despite the authenticity score.";

function normalizeDecisionReason(params: {
  decision: AgentLog["decision"];
  decisionReason: string | null;
  rawText: string | null;
}): string | null {
  const { decision, decisionReason, rawText } = params;
  const reason = decisionReason?.trim() || null;
  if (decision !== "REJECTED") return reason;

  const haystack = `${rawText ?? ""} ${reason ?? ""}`.toLowerCase();
  const mentionsOverseas =
    haystack.includes("overseas") ||
    haystack.includes("outside singapore") ||
    haystack.includes("out of singapore") ||
    haystack.includes("not in singapore") ||
    haystack.includes("foreign country") ||
    haystack.includes("direct public-safety risk in singapore");

  if (mentionsOverseas) {
    return OVERSEAS_DECISION_REASON;
  }

  if (!reason) {
    return "This report was rejected because it does not meet the publication criteria for a Singapore petty-crime or public-safety incident.";
  }

  if (reason.toLowerCase().includes("retry limit reached")) {
    return "This report was rejected after repeated retries because the system could not obtain enough reliable incident detail to publish it.";
  }

  if (reason.toLowerCase().includes("llm output invalid")) {
    return "This report was rejected as a safety fallback because the decision model output was invalid or incomplete.";
  }

  return reason;
}

function extractAgentContent(m: Record<string, unknown>): string {
  const lines: string[] = [];

  const primary = typeof m.note === "string" ? m.note
    : typeof m.reasoning === "string" ? m.reasoning
    : typeof m.content === "string" ? m.content
    : null;
  if (primary) lines.push(primary);

  if (typeof m.decision_reason === "string" && m.decision_reason) {
    lines.push(m.decision_reason);
  }

  if (typeof m.incident_summary_used === "string" && m.incident_summary_used)
    lines.push(`used: "${m.incident_summary_used}"`);

  if (m.candidate_scores && typeof m.candidate_scores === "object") {
    const scores = m.candidate_scores as Record<string, number>;
    const top3 = Object.entries(scores)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 3)
      .map(([k, v]) => `${k.replace(/_/g, " ")} ${(v * 100).toFixed(1)}%`)
      .join(" · ");
    lines.push(`scores: ${top3}`);
  }

  // Split rubric features into ✓ / ✗ groups for readability.
  if (m.features && typeof m.features === "object") {
    const features = m.features as Record<string, boolean>;
    const yes = Object.entries(features).filter(([, v]) => v).map(([k]) => k.replace(/_/g, " "));
    const no  = Object.entries(features).filter(([, v]) => !v).map(([k]) => k.replace(/_/g, " "));
    if (yes.length) lines.push(`✓ ${yes.join(", ")}`);
    if (no.length)  lines.push(`✗ ${no.join(", ")}`);
  }

  if (m.extracted_fields && typeof m.extracted_fields === "object") {
    const f = m.extracted_fields as Record<string, unknown>;
    const parts = (["location", "time", "action"] as const)
      .filter((k) => f[k] != null && String(f[k]) !== "null")
      .map((k) => `${k}: ${f[k]}`);
    if (parts.length) lines.push(parts.join(" · "));
  }

  if (typeof m.instruction === "string" && m.instruction) lines.push(m.instruction);
  if (typeof m.reason      === "string" && m.reason)      lines.push(m.reason);

  // Last-resort fallback if no standard fields were present.
  if (lines.length === 0 && typeof m.raw_output === "string" && m.raw_output)
    lines.push(m.raw_output);

  return lines.join("\n");
}

function rowToAgentLog(r: DbRow): AgentLog {
  // agent_messages is a JSONB array aggregated by the incident_full view — already parsed.
  let raw: Record<string, unknown>[] = [];
  if (Array.isArray(r.agent_messages)) {
    raw = r.agent_messages as Record<string, unknown>[];
  }

  // Prefer the top-level decision_reason from incident_decisions (via the view),
  // falling back to any decision_reason embedded inside individual message rows.
  const parsedDecisionReason: string | null =
    (typeof r.decision_reason === "string" && r.decision_reason)
      ? r.decision_reason
      : (raw.find((m) =>
          (m.agent === "decision" || m.agent === "decision_agent") &&
          typeof m.decision_reason === "string"
        )
          ?.decision_reason as string | undefined) ?? null;
  const decision = mapDecisionToAgentDecision(r.decision, r.status);
  const decision_reason = normalizeDecisionReason({
    decision,
    decisionReason: parsedDecisionReason,
    rawText: r.raw_text,
  });

  const messages: AgentMessage[] = raw.map((m) => {
    const agent = typeof m.agent === "string" ? m.agent
      : typeof m.role === "string" ? m.role
      : "unknown";

    let content = extractAgentContent(m);
    if (agent === "crawler" && r.raw_text) {
      content = content
        ? `${content}\nraw text: ${r.raw_text}`
        : `raw text: ${r.raw_text}`;
    }

    return { agent, content };
  });

  if (r.raw_text && !messages.some((m) => m.agent === "crawler")) {
    messages.unshift({
      agent: "crawler",
      content: `raw text: ${r.raw_text}`,
    });
  }

  return {
    id: r.incident_id,
    incident_id: r.incident_id,
    cleaned_content: r.cleaned_content,
    raw_text: r.raw_text,
    scraped_at: r.created_at ?? new Date().toISOString(),
    source: r.source_platform ?? "unknown",
    source_url: r.source_url ?? null,
    decision,
    decision_reason,
    messages,
  };
}

// Zustand store
export type CrimeTypeFilter = "all" | (string & {});

export type TimeRangeFilter = "24h" | "7d" | "30d" | "90d" | "all";
export type SeverityFilter = "all" | "critical_only" | "no_location";

interface SafeWatchState {
  incidents: Incident[];
  clusters: Cluster[];
  selectedIncidentId: string | null;
  agentLogsOpen: boolean;
  setAgentLogsOpen: (open: boolean) => void;
  agentLogs: AgentLog[];
  selectedClusterId: string | null;
  crimeType: CrimeTypeFilter;
  timeRange: TimeRangeFilter;
  severityFilter: SeverityFilter;
  mapFlyTo: { lat: number; lng: number; zoom: number; key: number } | null;
  sidebarCollapsed: boolean;
  isLoading: boolean;

  toggleSidebar: () => void;
  selectIncident: (id: string | null) => void;
  selectCluster: (id: string | null) => void;
  setCrimeType: (v: CrimeTypeFilter) => void;
  setTimeRange: (v: TimeRangeFilter) => void;
  setSeverityFilter: (v: SeverityFilter) => void;
  flyTo: (lat: number, lng: number, zoom?: number) => void;
  loadIncidents: () => Promise<void>;
  loadAgentLogs: () => Promise<void>;
  subscribeRealtime: () => () => void;
}

export const useStore = create<SafeWatchState>((set) => ({
  // Start with mock data so the map is never blank on first load.
  // loadIncidents() will replace this with real Supabase data.
  incidents: mockIncidents,
  clusters:  mockClusters,

  selectedIncidentId: null,
  selectedClusterId:  null,
  crimeType:          "all",
  timeRange:          "all",
  severityFilter:     "all",
  mapFlyTo:           null,
  isLoading:          false,

  sidebarCollapsed:
    typeof window !== "undefined" && window.innerWidth < 640,
  agentLogsOpen: false,
  agentLogs: [],
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setAgentLogsOpen: (open) => set({ agentLogsOpen: open }),
  selectIncident: (id) => set({ selectedIncidentId: id }),
  selectCluster: (id) => set({ selectedClusterId: id }),
  setCrimeType: (v) => set({ crimeType: v }),
  setTimeRange: (v) => set({ timeRange: v }),
  setSeverityFilter: (v) => set({ severityFilter: v }),
  flyTo: (lat, lng, zoom = 15) =>
    set({ mapFlyTo: { lat, lng, zoom, key: Date.now() } }),

  subscribeRealtime: () => {
    // Listen on incident_queue for status updates — when an incident becomes
    // "processed" it should appear on the map. Re-fetch the full row from the
    // view so all joined fields are available.
    const channel = supabase
      .channel("incidents-realtime")
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "incident_queue", filter: "status=eq.processed" },
        async (payload) => {
          const incident_id = (payload.new as { incident_id?: string }).incident_id;
          if (!incident_id) return;
          const { data } = await supabase
            .from("incident_full")
            .select("incident_id, source_platform, source_url, raw_text, cleaned_content, status, category, authenticity_score, severity, location_text, latitude, longitude, timestamp_text, normalized_time, created_at, decision, decision_reason, agent_messages")
            .eq("incident_id", incident_id)
            .single();
          if (data) {
            const row = data as DbRow;
            const newIncident = rowToIncident(row);
            const newLog = rowToAgentLog(row);
            set((s) => ({
              incidents: [newIncident, ...s.incidents.filter((i) => i.id !== row.incident_id)],
              agentLogs: [newLog, ...s.agentLogs.filter((l) => l.id !== row.incident_id)],
            }));
          }
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  },

  loadIncidents: async () => {
    set({ isLoading: true });

    const { data, error } = await supabase
      .from("incident_full")
      .select("incident_id, source_platform, source_url, raw_text, cleaned_content, status, category, authenticity_score, severity, location_text, latitude, longitude, timestamp_text, normalized_time, created_at")
      .eq("status", "processed")
      .order("created_at", { ascending: false })
      .limit(200);

    if (error) {
      console.error("Failed to load incidents from Supabase:", error.message);
      set({ incidents: mockIncidents, isLoading: false });
      return;
    }

    const incidents = (data as unknown as DbRow[]).map(rowToIncident);

    if (incidents.length > 0) {
      console.log(`Loaded ${incidents.length} incidents from Supabase.`);
      set({ incidents, isLoading: false });
    } else {
      console.warn("No incidents in Supabase yet. Showing mock data.");
      set({ incidents: mockIncidents, isLoading: false });
    }
  },
  loadAgentLogs: async () => {
    const { data, error } = await supabase
      .from("incident_full")
      .select("incident_id, source_platform, source_url, cleaned_content, raw_text, status, decision, decision_reason, agent_messages, created_at")
      .in("status", ["processed", "rejected"])
      .not("cleaned_content", "is", null)
      .order("created_at", { ascending: false })
      .limit(200);

    if (error) {
      console.error("Failed to load agent logs from Supabase:", error.message);
      return;
    }

    console.log("Supabase agent logs response:", data);
    const agentLogs = (data as DbRow[]).map(rowToAgentLog);
    console.log("Mapped agent logs:", agentLogs.length);
    set({ agentLogs });
  },
}));

// Derived selectors
const TIME_RANGE_HOURS: Record<Exclude<TimeRangeFilter, "all">, number> = {
  "24h": 24,
  "7d":  24 * 7,
  "30d": 24 * 30,
  "90d": 24 * 90,
};

export function useFilteredIncidents(): Incident[] {
  const { incidents, crimeType, timeRange } = useStore();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  return useMemo(() => {
    const cutoff =
      timeRange === "all"
        ? null
        : now - TIME_RANGE_HOURS[timeRange] * 3600 * 1000;

    return incidents.filter((i) => {
      if (crimeType !== "all" && i.type !== crimeType) return false;
      if (cutoff === null) return true;
      const postedAt = new Date(i.timestamp).getTime();
      if (Number.isNaN(postedAt)) return true;
      return postedAt >= cutoff;
    });
  }, [crimeType, incidents, now, timeRange]);
}

export function severityCounts(incidents: Incident[]): Record<Severity, number> {
  const out: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const i of incidents) out[i.severity]++;
  return out;
}

export function timeAgo(iso: string): string {
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "Unknown time";
  const diffMs = Date.now() - time;
  const mins = Math.round(diffMs / 60000);
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function formatTimestamp(iso: string): string {
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) return "Unknown time";
  return time.toLocaleString("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
