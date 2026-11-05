// Starting a match: the server opens it, gets the court picture, and the court is marked on that
// picture before any video is sent. The video follows when it's ready.
import { apiPost, apiPostPicture, type Creds } from './api';
import { BYTES_PER_MINUTE, MAX_RECORDING_MINUTES, PART_BYTES } from './config';

export type MatchType = 'singles' | 'doubles';
export type MatchInfo = { type: MatchType; near: string; far: string };

export async function beginMatch(stillUri: string, creds: Creds, size = 0): Promise<{ job: string; r2: boolean }> {
  const init = await apiPost<{ job_id: string; r2: boolean }>('/api/upload/init', { size, chunk_size: PART_BYTES, later: 1 }, creds);
  await apiPostPicture(`/api/upload/${init.job_id}/frame`, stillUri, {}, creds);
  return { job: init.job_id, r2: init.r2 };
}

// The website's court-marking screen, on its own. auto: mark by itself if the court is found.
export function markPath(job: string, { type, near, far }: MatchInfo, auto: boolean): string {
  const q = new URLSearchParams({ mark: job, type, p1: near, p2: far });
  if (auto) q.set('auto', '1');
  return `/new?${q.toString()}`;
}

export const matchTitle = ({ near, far }: MatchInfo) => `${near.trim() || 'Player 1'} vs ${far.trim() || 'Player 2'}`;

export const roomMinutes = (freeBytes: number) => Math.floor(freeBytes / BYTES_PER_MINUTE);

export function spaceWarning(freeBytes: number): { block: boolean; text: string } | null {
  const minutes = roomMinutes(freeBytes);
  if (minutes >= MAX_RECORDING_MINUTES) return null;
  if (minutes < 10) return { block: true, text: `This phone only has room for about ${minutes} minutes of video. Free up some space first.` };
  return { block: false, text: `This phone has room for about ${minutes} minutes of video, so a long match may not fit.` };
}

export type Unsent = { job: string; r2: boolean; path: string; title: string };
export const UNSENT_KEY = 'activeRecording';
