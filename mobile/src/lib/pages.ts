// How website pages behave inside the app. The pages are the site's own phone pages; these rules
// tell them they're in the app, and send their links to the right native place.
import { API_BASE } from './config';
import type { Scheme } from './theme';

export type PageState = { session: string | null; passcode: string | null; role?: string; theme: Scheme; page?: string };

// Runs before a page's own scripts: site.js reads window.AdvantageApp and drops the website's
// header and footer, and the page finds the sign-in where it always looks for it.
export function appScript({ session, passcode, role, theme, page }: PageState): string {
  const set = (key: string, value: string | null | undefined) =>
    value ? `localStorage.setItem(${JSON.stringify(key)},${JSON.stringify(value)});` : `localStorage.removeItem(${JSON.stringify(key)});`;
  // Dark or light from the very first paint, so a reload never flashes white in dark mode.
  const first = `var d=document.documentElement;d.dataset.app="1";d.dataset.theme=${JSON.stringify(theme)};d.style.colorScheme=${JSON.stringify(theme)};${page ? `d.style.backgroundColor=${JSON.stringify(page)};` : ''}`;
  return `window.AdvantageApp={theme:${JSON.stringify(theme)}};
try{${first}}catch(e){}
document.addEventListener('DOMContentLoaded',function(){requestAnimationFrame(function(){window.ReactNativeWebView&&window.ReactNativeWebView.postMessage('{"type":"painted"}');});});
try{${set('advantage_session', session)}${set('tennis_passcode', passcode)}${set('advantage_role', role)}}catch(e){}
true;`;
}

export const themeScript = (theme: Scheme, page?: string) =>
  `${page ? `document.documentElement.style.backgroundColor=${JSON.stringify(page)};document.documentElement.style.colorScheme=${JSON.stringify(theme)};` : ''}window.Site&&Site.setTheme&&Site.setTheme(${JSON.stringify(theme)});true;`;

export type Route =
  | { go: 'stay' }
  | { go: 'tab'; tab: 'dashboard' | 'matches' | 'record' | 'account'; pick?: boolean }
  | { go: 'report'; job: string; watch: boolean }
  | { go: 'page'; path: string }
  | { go: 'outside'; url: string };

// Where a tapped link goes. `here` is the path this screen is showing.
export function routeFor(url: string, here: string): Route {
  if (url === 'about:blank' || url.startsWith('blob:') || url.startsWith('data:')) return { go: 'stay' };
  if (!url.startsWith(API_BASE)) return { go: 'outside', url };
  const rest = url.slice(API_BASE.length) || '/';
  const [pathAndQuery, hash = ''] = rest.split('#');
  const [path, query = ''] = pathAndQuery.split('?');
  const [herePath] = here.split(/[?#]/);
  if (path === herePath && (path !== '/app' || !hash)) return { go: 'stay' };

  if (herePath === '/example' && path === '/report') return { go: 'stay' };   // the site's own redirect
  if (path === '/report' || path === '/report.html') {
    const params = new URLSearchParams(query);
    const job = params.get('job');
    return job ? { go: 'report', job, watch: params.get('watch') === '1' } : { go: 'stay' };
  }
  if (path === '/app') return { go: 'tab', tab: hash === 'matches' ? 'matches' : 'dashboard' };
  if (path === '/account') return { go: 'tab', tab: 'account' };
  if (path === '/new') {
    if (hash === 'filmGuide') return { go: 'page', path: '/new#filmGuide' };
    return { go: 'tab', tab: 'record', pick: hash === 'new' };
  }
  return { go: 'page', path: rest };
}

export type PageMessage =
  | { type: 'session'; token: string | null }
  | { type: 'passcode'; code: string }
  | { type: 'painted' }
  | { type: 'marked' }
  | { type: 'mark-check' }
  | { type: 'print'; html: string };

export function readMessage(raw: string): PageMessage | null {
  try {
    const m = JSON.parse(raw);
    return m && typeof m.type === 'string' ? (m as PageMessage) : null;
  } catch {
    return null;
  }
}
