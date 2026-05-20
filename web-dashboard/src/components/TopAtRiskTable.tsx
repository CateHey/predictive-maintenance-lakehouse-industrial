"use client";

import type { Prediction } from "@/types";
import { getRiskColor } from "@/lib/utils";

interface Props {
  data: Prediction[];
}

export default function TopAtRiskTable({ data }: Props) {
  const top10 = data
    .filter((p) => p.risk !== "HEALTHY")
    .sort((a, b) => a.predicted_rul - b.predicted_rul)
    .slice(0, 10);

  return (
    <div className="glass-card p-5">
      <h3 className="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">
        Top 10 At-Risk Units
      </h3>
      <div className="space-y-2">
        {top10.map((p) => {
          const rs = getRiskColor(p.risk);
          const barPct = Math.min(100, (p.predicted_rul / 125) * 100);
          return (
            <div
              key={p.unit_id}
              className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-card-hover transition-colors"
            >
              <span className="font-mono text-sm w-16">Unit {p.unit_id}</span>
              <div className="flex-1 h-2 bg-border/30 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${barPct}%`,
                    background: p.risk === "CRITICAL" ? "#ef4444" : "#f59e0b",
                  }}
                />
              </div>
              <span className="font-mono text-xs text-muted-foreground w-12 text-right">
                {p.predicted_rul}
              </span>
              <div className={`w-2 h-2 rounded-full ${rs.dot}`} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
