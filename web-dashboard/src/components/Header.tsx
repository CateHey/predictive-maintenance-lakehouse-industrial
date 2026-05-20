"use client";

import { Activity, Database, Cpu } from "lucide-react";

export default function Header() {
  return (
    <header className="border-b border-border/50 bg-card/50 backdrop-blur-xl sticky top-0 z-50">
      <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan/10 border border-cyan/20 flex items-center justify-center">
            <Cpu className="w-5 h-5 text-cyan" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              Predictive Maintenance
            </h1>
            <p className="text-xs text-muted-foreground">
              Industrial OPS Center
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Database className="w-3.5 h-3.5" />
            <span>NASA C-MAPSS FD001</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Activity className="w-3.5 h-3.5" />
            <span>Medallion Architecture</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="pulse-dot bg-green" />
            <span className="text-xs text-green font-medium">
              System Online
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
