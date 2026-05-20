import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getRiskColor(risk: string) {
  switch (risk) {
    case "CRITICAL":
      return { bg: "bg-red/10", text: "text-red", border: "border-red/30", dot: "bg-red" };
    case "WARNING":
      return { bg: "bg-amber/10", text: "text-amber", border: "border-amber/30", dot: "bg-amber" };
    case "HEALTHY":
      return { bg: "bg-green/10", text: "text-green", border: "border-green/30", dot: "bg-green" };
    default:
      return { bg: "bg-muted/10", text: "text-muted", border: "border-muted/30", dot: "bg-muted" };
  }
}

export function getRiskChartColor(risk: string) {
  switch (risk) {
    case "CRITICAL": return "#ef4444";
    case "WARNING": return "#f59e0b";
    case "HEALTHY": return "#10b981";
    default: return "#64748b";
  }
}
