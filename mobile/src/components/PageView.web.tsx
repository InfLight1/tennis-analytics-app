// Browser stand-in, only used to look at the native screens on a computer.
import { API_BASE } from '@/lib/config';
import type { PageMessage } from '@/lib/pages';

export function PageView({ path }: { path: string; onMessage?: (m: PageMessage) => void; reloadOnFocus?: boolean }) {
  return <iframe title="Page" src={`${API_BASE}${path}`} style={{ flex: 1, border: 0, width: '100%', height: '100%' }} />;
}
