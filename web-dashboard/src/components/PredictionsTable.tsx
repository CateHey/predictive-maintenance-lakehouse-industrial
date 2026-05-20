"use client";

import { useState } from "react";
import { ArrowUpDown, Download, Search } from "lucide-react";
import type { Prediction } from "@/types";
import { getRiskColor } from "@/lib/utils";

interface Props {
  data: Prediction[];
}

type SortKey = "unit_id" | "predicted_rul" | "current_cycle" | "risk";
type SortDir = "asc" | "desc";

export default function PredictionsTable({ data }: Props) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("predicted_rul");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const riskOrder = { CRITICAL: 0, WARNING: 1, HEALTHY: 2 };

  const filtered = data
    .filter((p) => String(p.unit_id).includes(search))
    .sort((a, b) => {
      let cmp: number;
      if (sortKey === "risk") {
        cmp =
          (riskOrder[a.risk as keyof typeof riskOrder] ?? 3) -
          (riskOrder[b.risk as keyof typeof riskOrder] ?? 3);
      } else {
        cmp = a[sortKey] - b[sortKey];
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

  const downloadCSV = () => {
    const headers = [
      "unit_id",
      "current_cycle",
      "predicted_rul",
      "risk",
      "s2",
      "s3",
      "s4",
      "s11",
      "s12",
    ];
    const rows = filtered.map((p) =>
      headers.map((h) => p[h as keyof Prediction]).join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "predictions.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const critCount = data.filter((d) => d.risk === "CRITICAL").length;
  const warnCount = data.filter((d) => d.risk === "WARNING").length;
  const healthyCount = data.filter((d) => d.risk === "HEALTHY").length;

  return (
    <div className="space-y-4 fade-in">
      {/* Alert summary cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Critical", count: critCount, color: "red" },
          { label: "Warning", count: warnCount, color: "amber" },
          { label: "Healthy", count: healthyCount, color: "green" },
        ].map((item) => (
          <div
            key={item.label}
            className={`glass-card p-4 border-l-2 border-l-${item.color}`}
          >
            <p className="text-xs text-muted-foreground uppercase tracking-wider">
              {item.label}
            </p>
            <p className={`text-2xl font-bold font-mono text-${item.color}`}>
              {item.count}
            </p>
          </div>
        ))}
      </div>

      {/* Table controls */}
      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
            <input
              type="text"
              placeholder="Search unit ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-4 py-2 bg-background border border-border rounded-lg text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-cyan/50 w-64"
            />
          </div>
          <button
            onClick={downloadCSV}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan/10 border border-cyan/30 text-cyan text-sm hover:bg-cyan/20 transition-colors"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {(
                  [
                    ["unit_id", "Unit ID"],
                    ["current_cycle", "Current Cycle"],
                    ["predicted_rul", "Predicted RUL"],
                    ["risk", "Risk Level"],
                  ] as [SortKey, string][]
                ).map(([key, label]) => (
                  <th
                    key={key}
                    onClick={() => toggleSort(key)}
                    className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:text-foreground transition-colors"
                  >
                    <span className="flex items-center gap-1">
                      {label}
                      <ArrowUpDown className="w-3 h-3" />
                    </span>
                  </th>
                ))}
                <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Key Sensors
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => {
                const rs = getRiskColor(p.risk);
                return (
                  <tr
                    key={p.unit_id}
                    className="border-b border-border/30 hover:bg-card-hover transition-colors"
                  >
                    <td className="py-3 px-4 font-mono font-medium">
                      {p.unit_id}
                    </td>
                    <td className="py-3 px-4 font-mono text-muted-foreground">
                      {p.current_cycle}
                    </td>
                    <td className="py-3 px-4">
                      <span className="font-mono font-medium">
                        {p.predicted_rul}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${rs.bg} ${rs.text} ${rs.border} border`}
                      >
                        <div className={`w-1.5 h-1.5 rounded-full ${rs.dot}`} />
                        {p.risk}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex gap-3 text-xs text-muted-foreground font-mono">
                        <span>S2:{p.s2}</span>
                        <span>S3:{p.s3}</span>
                        <span>S11:{p.s11}</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <p className="text-xs text-muted mt-3">
          Showing {filtered.length} of {data.length} units
        </p>
      </div>
    </div>
  );
}
