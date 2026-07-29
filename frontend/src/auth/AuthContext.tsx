import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken } from "../api/client";

export interface User {
  username: string;
  role: string;
}

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      if (getToken()) {
        try {
          const me = await api<User>("/auth/me");
          if (active) setUser(me);
        } catch {
          setToken(null);
        }
      }
      if (active) setLoading(false);
    })();

    const onUnauthorized = () => setUser(null);
    window.addEventListener("cur:unauthorized", onUnauthorized);
    return () => {
      active = false;
      window.removeEventListener("cur:unauthorized", onUnauthorized);
    };
  }, []);

  async function login(username: string, password: string) {
    const res = await api<{ access_token: string; username: string; role: string }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ username, password }) },
    );
    setToken(res.access_token);
    setUser({ username: res.username, role: res.role });
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
