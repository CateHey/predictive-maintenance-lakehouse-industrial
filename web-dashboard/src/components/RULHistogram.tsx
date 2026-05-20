"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  CartesianGrid,
} from "recharts";
import type { RULDistribution } from "@/types";
import { getRiskChartColor } from "@/lib/utils";

interface Props {
  data: RULDistribution[];
}

export default function RULHistogram({ data }: Props) {
  const bins = [
    { range: "0-25", min: 0, max: 25 },
    { range: "26-50", min: 26, max: 50 },
    { range: "51-75", min: 51, max: 75 },
    { range: "76-100", min: 76, max: 100 },
    { range: "101-125", min: 101, max: 125 },
  ];

  const histogram = bins.map((bin) => {
    const count = data.filter((d) => d.rul >= bin.min && d.rul <= bin.max).length;
    const color =
      bin.max <= 50
        ? "#ef4444"
        : bin.max <= 100
          ? "#f59e0b"
          : "#10b981";
    return { ...bin, count, color };
  });

  return (
    <div className="glass-card p-5">
      <h3 className="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">
        RUL Distribution
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={histogram} barCategoryGap="20%">
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis
            dataKey="range"
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            axisLine={{ stroke: "#1e293b" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#0d1117",
              border: "1px solid #1e293b",
              borderRadius: 8,
              color: "#e2e8f0",
              fontSize: 13,
            }}
            formatter={(value) => [`${value} units`, "Count"]}
          />
          <Bar dataKey="count" radius={[6, 6, 0, 0]}>
            {histogram.map((entry, i) => (
              <Cell key={i} fill={entry.color} fillOpacity={0.8} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RiskDonut({ data }: Props) {
  const counts = {
    CRITICAL: data.filter((d) => d.risk === "CRITICAL").length,
    WARNING: data.filter((d) => d.risk === "WARNING").length,
    HEALTHY: data.filter((d) => d.risk === "HEALTHY").length,
  };

  const total = data.length;
  const segments = [
    { label: "Critical", value: counts.CRITICAL, color: "#ef4444", pct: ((counts.CRITICAL / total) * 100).toFixed(0) },
    { label: "Warning", value: counts.WARNING, color: "#f59e0b", pct: ((counts.WARNING / total) * 100).toFixed(0) },
    { label: "Healthy", value: counts.HEALTHY, color: "#10b981", pct: ((counts.HEALTHY / total) * 100).toFixed(0) },
  ];

  return (
    <div className="glass-card p-5">
      <h3 className="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">
        Risk Breakdown
      </h3>
      <div className="flex flex-col items-center gap-4">
        <div className="relative w-44 h-44">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            {(() => {
              let offset = 0;
              return segments.map((seg) => {
                const pct = (seg.value / total) * 100;
                const circumference = Math.PI * 36;
                const dashArray = `${(pct / 100) * circumference} ${circumference}`;
                const dashOffset = -(offset / 100) * circumference;
                offset += pct;
                return (
                  <circle
                    key={seg.label}
                    cx="50"
                    cy="50"
                    r="36"
                    fill="none"
                    stroke={seg.color}
                    strokeWidth="8"
                    strokeDasharray={dashArray}
                    strokeDashoffset={dashOffset}
                    strokeLinecap="round"
                    opacity={0.85}
                  />
                );
              });
            })()}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold font-mono">{total}</span>
            <span className="text-[10px] text-muted-foreground uppercase">
              units
            </span>
          </div>
        </div>
        <div className="flex gap-4">
          {segments.map((seg) => (
            <div key={seg.label} className="flex items-center gap-2 text-xs">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ background: seg.color }}
              />
              <span className="text-muted-foreground">{seg.label}</span>
              <span className="font-mono font-medium">{seg.pct}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
