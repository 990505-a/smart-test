import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Format a UTC datetime string from the backend as local Beijing time (yyyy-MM-dd HH:mm).
 * Backend stores UTC timestamps without timezone suffix, so we add 'Z' to force UTC parsing.
 */
export function formatUTCDate(utcStr: string | null | undefined): string {
  if (!utcStr) return "-"
  const normalized = utcStr.endsWith("Z") || utcStr.includes("+") ? utcStr : utcStr + "Z"
  return new Date(normalized).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).replace(/\//g, "-")
}
