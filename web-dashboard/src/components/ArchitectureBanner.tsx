"use client";

import { Database, Layers, Brain, BarChart3, ArrowRight } from "lucide-react";

const steps = [
  {
    icon: Database,
    label: "Bronze",
    desc: "Raw Ingestion",
    color: "text-amber",
    bg: "bg-amber/10",
  },
  {
    icon: Layers,
    label: "Silver",
    desc: "Quality Validated",
    color: "text-muted-foreground",
    bg: "bg-muted/10",
  },
  {
    icon: Brain,
    label: "Gold",
    desc: "ML Features",
    color: "text-amber",
    bg: "bg-amber/10",
  },
  {
    icon: BarChart3,
    label: "Predict",
    desc: "XGBoost + MLflow",
    color: "text-cyan",
    bg: "bg-cyan/10",
  },
];

export default function ArchitectureBanner() {
  return (
    <div className="glass-card p-5">
      <h3 className="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">
        Pipeline Architecture
      </h3>
      <div className="flex items-center justify-between">
        {steps.map((step, i) => (
          <div key={step.label} className="flex items-center gap-3">
            <div className="flex flex-col items-center gap-2">
              <div
                className={`w-12 h-12 rounded-xl ${step.bg} flex items-center justify-center`}
              >
                <step.icon className={`w-5 h-5 ${step.color}`} />
              </div>
              <div className="text-center">
                <p className="text-xs font-medium">{step.label}</p>
                <p className="text-[10px] text-muted">{step.desc}</p>
              </div>
            </div>
            {i < steps.length - 1 && (
              <ArrowRight className="w-4 h-4 text-border mx-2" />
            )}
          </div>
        ))}
      </div>
      <div className="mt-4 pt-3 border-t border-border/30">
        <div className="flex flex-wrap gap-2">
          {[
            "Delta Lake",
            "Databricks",
            "XGBoost",
            "MLflow",
            "NASA C-MAPSS",
          ].map((tech) => (
            <span
              key={tech}
              className="px-2 py-0.5 rounded-md bg-card-hover border border-border text-[10px] text-muted-foreground"
            >
              {tech}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
