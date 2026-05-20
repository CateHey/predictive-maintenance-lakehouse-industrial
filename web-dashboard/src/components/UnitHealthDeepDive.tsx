"use client";

import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Area,
  AreaChart,
} from "recharts";
import type { TimeseriesData, Prediction } from "@/types";
import { SENSOR_LABELS } from "@/types";
import { getRiskColor, getRiskChartColor } from "@/lib/utils";

interface Props {
  timeseries: TimeseriesData;
  predictions: Prediction[];
}

const CHART_COLORS = [
  "#06b6d4",
  "#f59e0b",
  "#10b981",
  "#3b82f6",
  "#a855f7",
  "#ec4899",
];

const sensorKeys = Object.keys(SENSOR_LABELS);

export default function UnitHealthDeepDive({ timeseries, predictions }: Props) {
  const [selectedUnit, setSelectedUnit] = useState("1");
  const [selectedSensors, setSelectedSensors] = useState<string[]>([
    "s2",
    "s3",
    "s4",
  ]);

  const unitData = timeseries[selectedUnit] || [];
  const unitPred = predictions.find(
    (p) => p.unit_id === parseInt(selectedUnit)
  );
  const risk = unitPred?.risk || "HEALTHY";
  const riskStyle = getRiskColor(risk);

  const toggleSensor = (s: string) => {
    setSelectedSensors((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s].slice(-6)
    );
  };

  const rulPct = unitPred ? Math.min(100, (unitPred.predicted_rul / 125) * 100) : 0;
  const gaugeColor = getRiskChartColor(risk);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 fade-in">
      {/* Sidebar - Unit selector */}
      <div className="glass-card p-4 lg:col-span-1">
        <h3 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wider">
          Select Unit
        </h3>
        <div className="max-h-[500px] overflow-y-auto space-y-1 pr-1">
          {predictions.map((p) => {
            const rs = getRiskColor(p.risk);
            return (
              <button
                key={p.unit_id}
                onClick={() => setSelectedUnit(String(p.unit_id))}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all flex items-center justify-between ${
                  String(p.unit_id) === selectedUnit
                    ? "bg-cyan/10 border border-cyan/30 text-cyan"
                    : "hover:bg-card-hover border border-transparent"
                }`}
              >
                <span className="font-mono">Unit {p.unit_id}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-muted-foreground">
                    RUL {p.predicted_rul}
                  </span>
                  <div className={`w-2 h-2 rounded-full ${rs.dot}`} />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main content */}
      <div className="lg:col-span-3 space-y-4">
        {/* Unit status header */}
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xl font-semibold">
                Unit {selectedUnit}
              </h3>
              <p className="text-sm text-muted-foreground">
                Cycle {unitPred?.current_cycle} of{" "}
                {unitPred?.max_cycle} max
              </p>
            </div>
            <div
              className={`px-4 py-2 rounded-full text-sm font-medium ${riskStyle.bg} ${riskStyle.text} ${riskStyle.border} border`}
            >
              {risk}
            </div>
          </div>

          {/* RUL Gauge */}
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="flex justify-between text-xs text-muted-foreground mb-1">
                <span>Predicted RUL</span>
                <span className="font-mono">{unitPred?.predicted_rul} cycles</span>
              </div>
              <div className="h-3 bg-border/50 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${rulPct}%`,
                    background: `linear-gradient(90deg, ${gaugeColor}dd, ${gaugeColor}88)`,
                  }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-muted mt-1">
                <span>0 (failure)</span>
                <span>125 (healthy)</span>
              </div>
            </div>
          </div>
        </div>

        {/* RUL Degradation Trajectory */}
        <div className="glass-card p-5">
          <h3 className="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">
            RUL Degradation Trajectory
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={unitData}>
              <defs>
                <linearGradient id="rulGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={gaugeColor} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={gaugeColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="cycle"
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                axisLine={{ stroke: "#1e293b" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                domain={[0, 130]}
              />
              <Tooltip
                contentStyle={{
                  background: "#0d1117",
                  border: "1px solid #1e293b",
                  borderRadius: 8,
                  color: "#e2e8f0",
                  fontSize: 12,
                }}
              />
              <Area
                type="monotone"
                dataKey="rul"
                stroke={gaugeColor}
                fill="url(#rulGradient)"
                strokeWidth={2}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Sensor selector */}
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Sensor Readings
            </h3>
            <span className="text-[10px] text-muted">
              Select up to 6 sensors
            </span>
          </div>
          <div className="flex flex-wrap gap-2 mb-4">
            {sensorKeys.map((s, i) => (
              <button
                key={s}
                onClick={() => toggleSensor(s)}
                className={`px-3 py-1 rounded-full text-xs transition-all border ${
                  selectedSensors.includes(s)
                    ? "border-cyan/40 bg-cyan/10 text-cyan"
                    : "border-border text-muted-foreground hover:border-muted-foreground"
                }`}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={unitData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="cycle"
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                axisLine={{ stroke: "#1e293b" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#94a3b8", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "#0d1117",
                  border: "1px solid #1e293b",
                  borderRadius: 8,
                  color: "#e2e8f0",
                  fontSize: 12,
                }}
              />
              {selectedSensors.map((s, i) => (
                <Line
                  key={s}
                  type="monotone"
                  dataKey={s}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  strokeWidth={1.5}
                  dot={false}
                  name={SENSOR_LABELS[s] || s}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
