"use client";

import { useState, useEffect } from "react";
import { LayoutDashboard, HeartPulse, Bell } from "lucide-react";
import Header from "./Header";
import KPICards from "./KPICards";
import RULHistogram, { RiskDonut } from "./RULHistogram";
import TopAtRiskTable from "./TopAtRiskTable";
import UnitHealthDeepDive from "./UnitHealthDeepDive";
import PredictionsTable from "./PredictionsTable";
import ArchitectureBanner from "./ArchitectureBanner";
import type { KPIs, RULDistribution, Prediction, TimeseriesData } from "@/types";

const tabs = [
  { id: "fleet", label: "Fleet Overview", icon: LayoutDashboard },
  { id: "health", label: "Unit Health", icon: HeartPulse },
  { id: "alerts", label: "Predictions & Alerts", icon: Bell },
] as const;

type TabId = (typeof tabs)[number]["id"];

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<TabId>("fleet");
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [rulDist, setRulDist] = useState<RULDistribution[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [timeseries, setTimeseries] = useState<TimeseriesData>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/data/kpis.json").then((r) => r.json()),
      fetch("/data/rul_distribution.json").then((r) => r.json()),
      fetch("/data/predictions.json").then((r) => r.json()),
      fetch("/data/timeseries.json").then((r) => r.json()),
    ]).then(([k, r, p, t]) => {
      setKpis(k);
      setRulDist(r);
      setPredictions(p);
      setTimeseries(t);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center grid-bg">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" />
          <p className="text-sm text-muted-foreground">
            Loading telemetry data...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen grid-bg">
      <Header />

      <main className="max-w-[1600px] mx-auto px-6 py-6">
        {/* Tab navigation */}
        <div className="flex gap-2 mb-6">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium border transition-all ${
                activeTab === id
                  ? "tab-active"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:bg-card-hover"
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === "fleet" && kpis && (
          <div className="space-y-4 fade-in">
            <KPICards data={kpis} />
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2">
                <RULHistogram data={rulDist} />
              </div>
              <RiskDonut data={rulDist} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <TopAtRiskTable data={predictions} />
              <ArchitectureBanner />
            </div>
          </div>
        )}

        {activeTab === "health" && (
          <UnitHealthDeepDive
            timeseries={timeseries}
            predictions={predictions}
          />
        )}

        {activeTab === "alerts" && <PredictionsTable data={predictions} />}
      </main>

      {/* Footer */}
      <footer className="border-t border-border/30 mt-8">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between text-xs text-muted">
          <span>Predictive Maintenance Lakehouse — Portfolio Project</span>
          <span>
            Medallion Architecture · XGBoost · MLflow · Delta Lake
          </span>
        </div>
      </footer>
    </div>
  );
}
