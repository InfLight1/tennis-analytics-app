// What the player sees about matches on their way to a report.
import { useCallback, useEffect, useRef, useState } from 'react';
import { listSends, onSendsChange, removeSend, updateSendSignIn, type Send } from '../../modules/advantage-send';
import { apiGet } from './api';
import { useAuth } from './auth';

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / 1e6))} MB`;
}

export function sendLine(s: Send): string {
  switch (s.phase) {
    case 'preparing': return 'Getting the video ready to send…';
    case 'sending': return `${formatBytes(s.sentBytes)} of ${formatBytes(s.totalBytes)} sent. Keeps going with the screen off.`;
    case 'finishing': return 'All sent. Finishing up…';
    case 'sign-in': return s.problem || 'Sign in again to keep sending.';
    case 'failed': return s.problem || "This video couldn't be sent.";
    case 'sent': return 'Sent. Working on your report…';
  }
}

export const sendShare = (s: Send) => (s.totalBytes ? Math.min(1, s.sentBytes / s.totalBytes) : 0);

export type Tracked = Send & { reportReady?: boolean; serverProblem?: string };
type Status = { stage?: string; message?: string; report_ready?: boolean };
const POLL_MS = 20_000;

// Sends in progress, plus finished ones still being analysed.
export function useSends() {
  const { creds, session, passcode } = useAuth();
  const [sends, setSends] = useState<Tracked[]>([]);
  const extra = useRef<Record<string, Partial<Tracked>>>({});

  const load = useCallback(async () => {
    const list = await listSends().catch(() => [] as Send[]);
    setSends(list.map((s) => ({ ...s, ...extra.current[s.jobId] })));
  }, []);

  useEffect(() => {
    load();
    const sub = onSendsChange(load);
    return () => sub.remove();
  }, [load]);

  useEffect(() => { updateSendSignIn(session, passcode).catch(() => {}); }, [session, passcode]);

  const sent = sends.filter((s) => s.phase === 'sent' && !s.reportReady && !s.serverProblem).map((s) => s.jobId).join();
  useEffect(() => {
    if (!sent) return;
    const check = async () => {
      for (const jobId of sent.split(',')) {
        const st = await apiGet<Status>(`/api/status/${jobId}`, creds).catch(() => null);
        if (!st) continue;
        if (st.report_ready || st.stage === 'done') extra.current[jobId] = { reportReady: true };
        else if (st.stage === 'error') extra.current[jobId] = { serverProblem: st.message || "This match couldn't be analysed." };
      }
      load();
    };
    check();
    const timer = setInterval(check, POLL_MS);
    return () => clearInterval(timer);
  }, [sent, creds, load]);

  const dismiss = useCallback(async (jobId: string) => {
    await removeSend(jobId).catch(() => {});
    delete extra.current[jobId];
    load();
  }, [load]);

  return { sends, dismiss };
}
