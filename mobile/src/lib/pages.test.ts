import { API_BASE } from './config';
import { appScript, readMessage, routeFor } from './pages';

const at = (path: string) => `${API_BASE}${path}`;

describe('routeFor', () => {
  it('stays on the page it is showing', () => {
    expect(routeFor(at('/app'), '/app')).toEqual({ go: 'stay' });
    expect(routeFor(at('/report?job=abc&x=1'), '/report?job=abc')).toEqual({ go: 'stay' });
  });
  it('opens a report on its own screen, with Watch the points kept', () => {
    expect(routeFor(at('/report?job=abc&watch=1'), '/app')).toEqual({ go: 'report', job: 'abc', watch: true });
    expect(routeFor(at('/report?job=abc'), '/app?view=matches')).toEqual({ go: 'report', job: 'abc', watch: false });
  });
  it('lets the example page follow the redirect to its report', () => {
    expect(routeFor(at('/report?job=e0'), '/example')).toEqual({ go: 'stay' });
  });
  it('sends the website tabs to the app tabs', () => {
    expect(routeFor(at('/app#matches'), '/app')).toEqual({ go: 'tab', tab: 'matches' });
    expect(routeFor(at('/account'), '/report?job=a')).toEqual({ go: 'tab', tab: 'account' });
    expect(routeFor(at('/new#record'), '/app')).toEqual({ go: 'tab', tab: 'record', pick: false });
    expect(routeFor(at('/new#new'), '/app')).toEqual({ go: 'tab', tab: 'record', pick: true });
  });
  it('keeps the filming guide and landing page links as pages', () => {
    expect(routeFor(at('/new#filmGuide'), '/app')).toEqual({ go: 'page', path: '/new#filmGuide' });
    expect(routeFor(at('/?stay=1#how'), '/app')).toEqual({ go: 'page', path: '/?stay=1#how' });
  });
  it('opens other sites outside the app', () => {
    expect(routeFor('https://example.com/a', '/app')).toEqual({ go: 'outside', url: 'https://example.com/a' });
  });
  it('lets the page load its own blobs', () => {
    expect(routeFor('blob:abc', '/report')).toEqual({ go: 'stay' });
  });
});

describe('appScript', () => {
  it('hands the sign-in to the page and marks it as the app', () => {
    const s = appScript({ session: 'tok"en', passcode: null, role: 'coach', theme: 'dark' });
    expect(s).toContain('window.AdvantageApp={theme:"dark"}');
    expect(s).toContain('localStorage.setItem("advantage_session","tok\\"en")');
    expect(s).toContain('localStorage.removeItem("tennis_passcode")');
    expect(s.trim().endsWith('true;')).toBe(true);
  });
  it('clears the sign-in on a signed-out page', () => {
    expect(appScript({ session: null, passcode: null, theme: 'light' })).toContain('localStorage.removeItem("advantage_session")');
  });
});

describe('readMessage', () => {
  it('reads messages and ignores anything else', () => {
    expect(readMessage('{"type":"marked"}')).toEqual({ type: 'marked' });
    expect(readMessage('nonsense')).toBeNull();
    expect(readMessage('{"a":1}')).toBeNull();
  });
});
