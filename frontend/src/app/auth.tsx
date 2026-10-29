import { useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { createContext, PropsWithChildren, useContext, useEffect, useState } from "react";

import { authStorage, api } from "../services/api";
import type { AuthResponse, AuthUser } from "../types/auth";

type AuthContextValue = {
  hasToken: boolean;
  isAuthenticated: boolean;
  isLoading: boolean;
  token: string | null;
  user: AuthUser | null;
  setSession: (session: AuthResponse) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function isInvalidSessionError(error: unknown) {
  return (
    axios.isAxiosError(error) &&
    (error.response?.status === 401 || error.response?.status === 403)
  );
}

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(() => authStorage.getToken());

  const meQuery = useQuery({
    queryKey: ["auth", "me", token],
    queryFn: ({ signal }) => api.fetchMe({ signal }),
    enabled: Boolean(token),
    initialData: () => {
      if (!token) {
        return undefined;
      }
      return (
        (queryClient.getQueryData(["auth", "me", token]) as AuthUser | undefined) ??
        authStorage.getUser(token) ??
        undefined
      );
    },
    initialDataUpdatedAt: 0,
    staleTime: 5 * 60_000,
    retry: (failureCount, error) => !isInvalidSessionError(error) && failureCount < 1,
  });

  const user = meQuery.data ?? null;
  const hasToken = Boolean(token);
  const isLoading = hasToken && !user && meQuery.isPending;
  const isAuthenticated = Boolean(token && user);

  function clearSession() {
    authStorage.clearToken();
    setToken(null);
    queryClient.removeQueries({ queryKey: ["auth"] });
    queryClient.removeQueries({ queryKey: ["saved-products"] });
    queryClient.removeQueries({ queryKey: ["saved-searches"] });
    queryClient.removeQueries({ queryKey: ["alerts"] });
    queryClient.removeQueries({ queryKey: ["admin-vendors"] });
  }

  useEffect(() => {
    if (token) {
      void api.wakeBackend().catch(() => undefined);
    }
  }, [token]);

  useEffect(() => {
    if (token && meQuery.data) {
      authStorage.setUser(token, meQuery.data);
    }
  }, [token, meQuery.data]);

  useEffect(() => {
    if (token && meQuery.isError && isInvalidSessionError(meQuery.error)) {
      clearSession();
    }
  }, [token, meQuery.isError, meQuery.error]);

  function setSession(session: AuthResponse) {
    authStorage.setToken(session.access_token);
    authStorage.setUser(session.access_token, session.user);
    setToken(session.access_token);
    queryClient.setQueryData(["auth", "me", session.access_token], session.user);
  }

  return (
    <AuthContext.Provider
      value={{
        hasToken,
        isAuthenticated,
        isLoading,
        token,
        user,
        setSession,
        signOut: clearSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}
