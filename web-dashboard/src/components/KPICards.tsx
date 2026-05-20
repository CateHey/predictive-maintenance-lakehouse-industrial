"use client";

import { Server, AlertTriangle, Gauge, ShieldAlert } from "lucide-react";
import type { KPIs } from "@/types";

interface KPICardsProps {
  data: KPIs;
}

const cards = [
  {
    key: "total_units" as const,
    label: "Total Units",
    icon: Server,
    color: "cyan" as const,
    format: (v: number) => v.toString(),
  },
  {
    key: "at_risk" as const,
    label: "Units At Risk",
    icon: AlertTriangle,
    color: "amber" as const,
    format: (v: number) => v.toString(),
  },
  {
    key: "avg_rul" as const,
    label: "Avg RUL (cycles)",
    icon: Gauge,
    color: "green" as const,
    format: (v: number) => v.toFixed(1),
  },
  {
    key: "critical" as const,
    label: "Critical Alerts",
    icon: ShieldAlert,
    color: "red" as const,
    format: (v: number) => v.toString(),
  },
];

export default function KPICards({ data }: KPICardsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map(({ key, label, icon: Icon, color, format }) => (
        <div key={key} className={`kpi-card ${color} glow-${color} p-5 fade-in`}>
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
                {label}
              </p>
              <p className="text-3xl font-bold font-mono tracking-tight">
                {format(data[key])}
              </p>
            </div>
            <div
              className={`w-10 h-10 rounded-lg bg-${color}/10 flex items-center justify-center`}
            >
              <Icon className={`w-5 h-5 text-${color}`} />
            </div>
          </div>
          {key === "at_risk" && (
            <p className="text-xs text-muted-foreground mt-2">
              {data.critical} critical · {data.warning} warning
            </p>
          )}
          {key === "total_units" && (
            <p className="text-xs text-muted-foreground mt-2">
              {data.healthy} healthy · {data.at_risk} at risk
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
