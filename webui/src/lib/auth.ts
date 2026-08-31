"use client";

// Auth token storage (用户模块). Token is opaque and validated server-side.

const TOKEN_KEY = "smart-test-platform-token";
const USER_KEY = "smart-test-platform-user";

export interface AuthUser {
  id: string;
  username: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuth(token: string, user: AuthUser): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}
