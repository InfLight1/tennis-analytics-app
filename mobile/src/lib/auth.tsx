// Who is signed in. Same accounts as the website; the sign-in is kept in the phone's secure storage.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError, apiGet, apiPost, type Creds } from './api';
import { store } from './store';

export type User = { username: string; name: string; role: 'player' | 'coach'; team_id: string | null };
export type Me = { user: User | null; team?: { name?: string; code?: string } };
type SignedIn = { session: string; user: User };

export type SignUp =
  | { kind: 'signin'; username: string; password: string }
  | { kind: 'join'; code: string; name: string; username: string; password: string }
  | { kind: 'solo'; name: string; username: string; password: string; email?: string; passcode: string }
  | { kind: 'coach'; team_name: string; name: string; username: string; password: string; passcode: string };

const ROUTES = { signin: '/api/auth/signin', join: '/api/auth/join', solo: '/api/auth/solo', coach: '/api/auth/create-team' };

type Auth = {
  ready: boolean;
  session: string | null;
  passcode: string | null;
  user: User | null;
  team: Me['team'];
  creds: Creds;
  enter: (form: SignUp) => Promise<void>;
  refresh: () => Promise<void>;
  setSession: (token: string | null) => void;
  setPasscode: (code: string) => void;
  signOut: () => Promise<void>;
  deleteAccount: () => Promise<void>;
};
const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [session, setSessionState] = useState<string | null>(null);
  const [passcode, setPasscodeState] = useState<string | null>(null);
  const [me, setMe] = useState<Me>({ user: null });

  const setSession = useCallback((token: string | null) => {
    setSessionState(token);
    store.set('session', token);
    if (!token) setMe({ user: null });
  }, []);
  const setPasscode = useCallback((code: string) => {
    setPasscodeState(code);
    store.set('passcode', code);
  }, []);

  const load = useCallback(async (token: string, code: string | null) => {
    const data = await apiGet<Me>('/api/me', { session: token, passcode: code });
    if (data.user) setMe(data);
    else setSession(null);            // the sign-in ran out
  }, [setSession]);

  useEffect(() => {
    (async () => {
      const [token, code] = await Promise.all([store.get('session'), store.get('passcode')]);
      setSessionState(token);
      setPasscodeState(code);
      if (token) await load(token, code).catch(() => {});   // no signal: stay signed in
      setReady(true);
    })();
  }, [load]);

  const enter = useCallback(async ({ kind, ...fields }: SignUp) => {
    const code = 'passcode' in fields ? fields.passcode.trim() : passcode;
    const form: Record<string, string | undefined> = { ...fields, passcode: undefined };
    const data = await apiPost<SignedIn>(ROUTES[kind], form, { passcode: code });
    if (code) setPasscode(code);
    setSession(data.session);
    await load(data.session, code);
  }, [load, passcode, setPasscode, setSession]);

  const refresh = useCallback(async () => {
    if (session) await load(session, passcode);
  }, [load, passcode, session]);

  const signOut = useCallback(async () => {
    await apiPost('/api/auth/signout', {}, { session, passcode }).catch(() => {});
    setSession(null);
  }, [passcode, session, setSession]);

  const deleteAccount = useCallback(async () => {
    try {
      await apiPost('/api/me/delete', {}, { session, passcode });
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) throw e;
    }
    setSession(null);
  }, [passcode, session, setSession]);

  const value = useMemo<Auth>(() => ({
    ready, session, passcode, user: me.user, team: me.team, creds: { session, passcode },
    enter, refresh, setSession, setPasscode, signOut, deleteAccount,
  }), [ready, session, passcode, me, enter, refresh, setSession, setPasscode, signOut, deleteAccount]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const a = useContext(AuthContext);
  if (!a) throw new Error('useAuth needs AuthProvider');
  return a;
}
