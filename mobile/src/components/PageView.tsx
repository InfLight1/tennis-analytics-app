// A website page inside the app: the site's own phone page, minus its header and footer.
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type Ref } from 'react';
import { Linking, View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import type { IOSWebViewProps } from 'react-native-webview/lib/WebViewTypes';
import { useAuth } from '@/lib/auth';
import { API_BASE } from '@/lib/config';
import { appScript, readMessage, routeFor, themeScript, type PageMessage, type Route } from '@/lib/pages';
import { savePdf } from '@/lib/pdf';
import { useTheme } from '@/lib/theme';
import { Body, Button, Title } from './ui';

const STALE_MS = 60_000;

// The library's combined phone props come out as `never` with this React Native's types.
const Web = WebView as unknown as ComponentType<IOSWebViewProps & { ref?: Ref<WebView> }>;

export function PageView({ path, onMessage, reloadOnFocus }: { path: string; onMessage?: (m: PageMessage) => void; reloadOnFocus?: boolean }) {
  const { colors, scheme } = useTheme();
  const { session, passcode, user, setSession, setPasscode } = useAuth();
  const router = useRouter();
  const web = useRef<WebView>(null);
  const loadedAt = useRef(0);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const script = useMemo(() => appScript({ session, passcode, role: user?.role, theme: scheme }), [session, passcode, user?.role, scheme]);

  useEffect(() => { web.current?.injectJavaScript(themeScript(scheme)); }, [scheme]);

  useFocusEffect(useCallback(() => {
    if (reloadOnFocus && loadedAt.current && Date.now() - loadedAt.current > STALE_MS) web.current?.reload();
  }, [reloadOnFocus]));

  const go = useCallback((route: Route) => {
    if (route.go === 'report') router.push({ pathname: '/report', params: { job: route.job, watch: route.watch ? '1' : '0' } });
    else if (route.go === 'page') router.push({ pathname: '/page', params: { path: route.path } });
    else if (route.go === 'outside') Linking.openURL(route.url).catch(() => {});
    else if (route.go === 'tab') {
      const tab = { dashboard: '/', matches: '/matches', record: '/record', account: '/account' }[route.tab];
      router.navigate((route.pick ? `${tab}?pick=1` : tab) as never);
    }
  }, [router]);

  const onPageMessage = useCallback((e: WebViewMessageEvent) => {
    const m = readMessage(e.nativeEvent.data);
    if (!m) return;
    if (m.type === 'session') setSession(m.token);
    if (m.type === 'passcode') setPasscode(m.code);
    if (m.type === 'print') savePdf(m.html).catch(() => {});
    onMessage?.(m);
  }, [onMessage, setPasscode, setSession]);

  if (failed) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.page, justifyContent: 'center', padding: 24, gap: 12 }}>
        <Title size={26}>No connection</Title>
        <Body muted>This page needs the internet. Anything you&apos;ve filmed is safe on this phone.</Body>
        <Button title="Try again" onPress={() => { setFailed(false); setAttempt((n) => n + 1); }} />
      </View>
    );
  }

  return (
    <Web
      key={attempt}
      ref={web}
      source={{ uri: `${API_BASE}${path}` }}
      injectedJavaScriptBeforeContentLoaded={script}
      applicationNameForUserAgent="AdvantageAIApp"
      style={{ flex: 1, backgroundColor: colors.page }}
      containerStyle={{ backgroundColor: colors.page }}
      contentInsetAdjustmentBehavior="never"
      automaticallyAdjustContentInsets={false}
      allowsInlineMediaPlayback
      mediaPlaybackRequiresUserAction={false}
      allowsLinkPreview={false}
      pullToRefreshEnabled
      sharedCookiesEnabled
      originWhitelist={['*']}
      onLoadEnd={() => { loadedAt.current = Date.now(); }}
      onError={() => setFailed(true)}
      onContentProcessDidTerminate={() => web.current?.reload()}
      onMessage={onPageMessage}
      onShouldStartLoadWithRequest={(req) => {
        if (!req.isTopFrame) return true;
        const route = routeFor(req.url, path);
        if (route.go === 'stay') return true;
        go(route);
        return false;
      }}
    />
  );
}
