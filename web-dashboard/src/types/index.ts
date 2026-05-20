export interface KPIs {
  total_units: number;
  critical: number;
  warning: number;
  healthy: number;
  avg_rul: number;
  at_risk: number;
}

export interface RULDistribution {
  unit_id: number;
  rul: number;
  risk: string;
  cycle: number;
  max_cycle: number;
}

export interface Prediction {
  unit_id: number;
  current_cycle: number;
  predicted_rul: number;
  risk: string;
  max_cycle: number;
  s2: number;
  s3: number;
  s4: number;
  s11: number;
  s12: number;
}

export interface TimeseriesPoint {
  cycle: number;
  rul: number;
  s2: number;
  s3: number;
  s4: number;
  s7: number;
  s8: number;
  s9: number;
  s11: number;
  s12: number;
  s13: number;
  s15: number;
  s17: number;
  s20: number;
  s21: number;
}

export type TimeseriesData = Record<string, TimeseriesPoint[]>;

export const SENSOR_LABELS: Record<string, string> = {
  s2: "LPC Outlet Temp",
  s3: "HPC Outlet Temp",
  s4: "LPT Outlet Temp",
  s7: "Total P @ HPC Out",
  s8: "Physical Fan Speed",
  s9: "Physical Core Speed",
  s11: "Static P @ HPC Out",
  s12: "Fuel/Air Ratio",
  s13: "Corrected Fan Speed",
  s15: "Bypass Ratio",
  s17: "Bleed Enthalpy",
  s20: "HPT Coolant Bleed",
  s21: "LPT Coolant Bleed",
};
