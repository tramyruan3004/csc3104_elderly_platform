"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  organiserLogin,
  organiserLogout,
  organiserRefresh,
  fetchOrganiserProfile,
  type OrganiserProfile,
  type TokenPair,
} from "../services/auth";

type AuthState = {
  user: OrganiserProfile | null;
  tokens: TokenPair | null;
  expiresAt: number | null;
};

type AuthContextValue = {
  user: OrganiserProfile | null;
  tokens: TokenPair | null;
  expiresAt: number | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const STORAGE_KEY = "organizer-auth-state";

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function computeExpiry(expiresIn: number | null | undefined) {
  if (!expiresIn || expiresIn <= 0) {
    return null;
  }
  return Date.now() + expiresIn * 1000;
}

function loadStoredState(): AuthState {
  if (typeof window === "undefined") {
    return { user: null, tokens: null, expiresAt: null };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { user: null, tokens: null, expiresAt: null };
    }
    const parsed = JSON.parse(raw) as AuthState;
    if (
      parsed.tokens?.access_token &&
      parsed.expiresAt &&
      parsed.expiresAt > Date.now()
    ) {
      return parsed;
    }
  } catch (error) {
    console.warn("Failed to parse stored auth state", error);
  }
  return { user: null, tokens: null, expiresAt: null };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => loadStoredState());
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (state.tokens?.access_token) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, [state]);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const hydrateProfile = useCallback(async (accessToken: string) => {
    const profile = await fetchOrganiserProfile({ accessToken });
    setState((prev) => ({
      ...prev,
      user: {
        id: profile.id,
        name: profile.name,
        nric: profile.nric,
        role: profile.role,
        org_ids: profile.org_ids ?? [],
      },
    }));
  }, []);

  const logout = useCallback(async () => {
    const tokens = state.tokens;
    try {
      if (tokens?.access_token && tokens.refresh_token) {
        await organiserLogout({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
        });
      }
    } catch (error) {
      console.warn("Logout request failed", error);
    } finally {
      clearRefreshTimer();
      setState({ user: null, tokens: null, expiresAt: null });
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    }
  }, [clearRefreshTimer, state.tokens]);

  const refreshSession = useCallback(async () => {
    const tokens = state.tokens;
    if (!tokens?.access_token || !tokens.refresh_token) {
      return;
    }
    try {
      const refreshed = await organiserRefresh({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
      const expiresAt = computeExpiry(refreshed.expires_in);
      setState((prev) => ({
        user: prev.user,
        tokens: refreshed,
        expiresAt,
      }));
      await hydrateProfile(refreshed.access_token);
    } catch (error) {
      console.warn("Organiser session refresh failed", error);
      await logout();
    }
  }, [hydrateProfile, logout, state.tokens]);

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await organiserLogin({ username, password });
      const expiresAt = computeExpiry(response.tokens.expires_in);
      setState({
        user: {
          id: response.user.id,
          name: response.user.name,
          nric: response.user.nric,
          role: response.user.role,
          org_ids: response.user.org_ids ?? [],
        },
        tokens: {
          access_token: response.tokens.access_token,
          refresh_token: response.tokens.refresh_token,
          expires_in: response.tokens.expires_in,
        },
        expiresAt,
      });
      await hydrateProfile(response.tokens.access_token).catch((error) =>
        console.warn("Failed to hydrate organiser profile after login", error)
      );
    },
    [hydrateProfile]
  );

  useEffect(() => {
    if (state.tokens?.access_token && !state.user) {
      hydrateProfile(state.tokens.access_token).catch((error) =>
        console.warn("Failed to fetch organiser profile", error)
      );
    }
  }, [hydrateProfile, state.tokens, state.user]);

  useEffect(() => {
    clearRefreshTimer();
    const tokens = state.tokens;
    const expiresAt = state.expiresAt;
    if (!tokens?.access_token || !tokens.refresh_token || !expiresAt) {
      return;
    }
    const now = Date.now();
    const msUntilExpiry = expiresAt - now;
    const REFRESH_BUFFER_MS = 60_000;
    const MIN_DELAY_MS = 5_000;
    const delay =
      msUntilExpiry <= REFRESH_BUFFER_MS
        ? MIN_DELAY_MS
        : Math.max(msUntilExpiry - REFRESH_BUFFER_MS, MIN_DELAY_MS);

    refreshTimerRef.current = setTimeout(() => {
      void refreshSession();
    }, delay);

    return () => {
      clearRefreshTimer();
    };
  }, [clearRefreshTimer, refreshSession, state.expiresAt, state.tokens]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: state.user,
      tokens: state.tokens,
      expiresAt: state.expiresAt,
      isAuthenticated: !!state.user && !!state.tokens?.access_token,
      login,
      logout,
    }),
    [login, logout, state]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return ctx;
}
