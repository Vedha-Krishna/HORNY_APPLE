import React, { useMemo } from "react";
import { ChevronDown, Shield } from "lucide-react";
import { useFilteredIncidents, useStore, severityCounts } from "./store";
import type { CrimeTypeFilter, TimeRangeFilter } from "./store";

const CRIME_LABELS: Record<string, string> = {
  snatch_theft: "Snatch theft",
  bike_theft:   "Bike theft",
  scam:         "Scams",
  vandalism:    "Vandalism",
  harassment:   "Harassment",
  theft:        "Theft",
  loan_shark:   "Loan shark",
};

const TIME_OPTIONS: { value: TimeRangeFilter; label: string }[] = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "all", label: "All" },
];

export default function Header() {
  const filtered = useFilteredIncidents();
  const counts = severityCounts(filtered);
  const { incidents, crimeType, timeRange, setCrimeType, setTimeRange } = useStore();
  const shownTotal = filtered.length;
  const loadedTotal = incidents.length;
  const isNarrowed = shownTotal !== loadedTotal;
  const crimeOptions = useMemo(() => {
    const types = new Set(
      incidents
        .map((incident) => incident.type)
        .filter((type): type is string => Boolean(type)),
    );

    if (crimeType !== "all") types.add(crimeType);

    return [
      { value: "all" as CrimeTypeFilter, label: "All crimes" },
      ...Array.from(types)
        .sort((a, b) => crimeLabel(a).localeCompare(crimeLabel(b)))
        .map((type) => ({
          value: type as CrimeTypeFilter,
          label: crimeLabel(type),
        })),
    ];
  }, [incidents, crimeType]);

  return (
    <header className="absolute top-2 left-2 right-2 sm:top-4 sm:left-4 sm:right-4 z-[1100] flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 sm:gap-3 pointer-events-none">
      <div className="flex w-full sm:w-auto items-center gap-2 sm:gap-3">
        {/* Logo / brand pill */}
        <div className="safewatch-glass-panel rounded-full pl-1.5 pr-3 sm:pr-4 py-1.5 flex items-center gap-2 pointer-events-auto h-10 sm:h-9 shrink-0">
          <div className="w-7 h-7 sm:w-6 sm:h-6 rounded-full bg-blue-500/15 border border-blue-500/30 flex items-center justify-center shrink-0">
            <Shield className="w-3.5 h-3.5 sm:w-3 sm:h-3 text-blue-400" />
          </div>
          <div className="flex flex-col leading-none gap-0.5">
            <span className="text-[12px] font-bold text-white tracking-wide">
              SafeWatch
            </span>
            <span className="hidden sm:inline text-[8px] text-slate-500 font-mono uppercase tracking-widest">
              Singapore
            </span>
          </div>
        </div>

        {/* Counts pill */}
        <div className="safewatch-glass-panel rounded-full px-3 sm:px-4 flex items-center justify-between sm:justify-start gap-2 sm:gap-3 pointer-events-auto h-10 sm:h-9 min-w-0 flex-1 sm:flex-none">
          <span className="hidden sm:inline text-[10px] font-mono uppercase text-slate-500">
            Showing
          </span>
          <span className="flex items-baseline gap-1 text-white tabular-nums shrink-0">
            <span className="text-sm font-bold">{shownTotal}</span>
            {isNarrowed && (
              <span className="hidden sm:inline text-[10px] font-mono text-slate-500">
                / {loadedTotal}
              </span>
            )}
          </span>
          <span className="w-px h-4 bg-white/10 shrink-0" />
          <div className="flex flex-1 sm:flex-none items-center justify-between sm:justify-start gap-2 sm:gap-3 min-w-0">
            <Dot color="#ef4444" count={counts.critical} label="Critical" />
            <Dot color="#f97316" count={counts.high} label="High" />
            <Dot color="#eab308" count={counts.medium} label="Medium" />
            <Dot color="#22c55e" count={counts.low} label="Low" />
          </div>
        </div>
      </div>

      {/* Filters pushed to right on wide, full-width on narrow */}
      <div className="sm:ml-auto safewatch-glass-panel rounded-full p-1 flex items-center gap-1 pointer-events-auto h-10 sm:h-9 w-full sm:w-auto max-w-full">
        <div className="min-w-0 flex-1 sm:flex-none">
          <Select
            value={crimeType}
            onChange={(v) => setCrimeType(v as CrimeTypeFilter)}
            options={crimeOptions}
          />
        </div>
        <span className="w-px h-4 bg-white/10 shrink-0" />
        <div className="grid grid-cols-5 shrink-0 gap-0.5">
          {TIME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setTimeRange(opt.value)}
              className={`min-w-9 h-8 sm:h-auto text-[10px] sm:text-[11px] font-mono uppercase px-1.5 sm:px-2.5 py-0.5 sm:py-1 rounded-full transition-colors ${
                timeRange === opt.value
                  ? "bg-white/10 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

function crimeLabel(type: string): string {
  return CRIME_LABELS[type] ?? titleCase(type);
}

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function Dot({
  color,
  count,
  label,
}: {
  color: string;
  count: number;
  label: string;
}) {
  return (
    <div className="flex items-center gap-1" title={`${label}: ${count}`}>
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
      />
      <span
        className="text-[11px] font-mono tabular-nums"
        style={{ color: count > 0 ? color : "#94a3b8" }}
      >
        {count}
      </span>
    </div>
  );
}

function Select<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="appearance-none bg-transparent border-0 pl-2.5 pr-7 py-1 text-[10px] sm:text-[11px] text-slate-100 font-mono uppercase tracking-wide hover:text-white focus:outline-none cursor-pointer w-full sm:w-auto max-w-full sm:max-w-none truncate"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} className="bg-[#0a0e17]">
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-300" />
    </div>
  );
}
