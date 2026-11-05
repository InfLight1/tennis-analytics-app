import { BarlowCondensed_700Bold, useFonts as useBoardFont } from '@expo-google-fonts/barlow-condensed';
import { Newsreader_500Medium, useFonts as useTitleFont } from '@expo-google-fonts/newsreader';
import { Stack } from 'expo-router';
import * as ScreenOrientation from 'expo-screen-orientation';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { useReportAlerts } from '@/lib/alerts';
import { AuthProvider, useAuth } from '@/lib/auth';
import { ThemeProvider, useTheme } from '@/lib/theme';

SplashScreen.preventAutoHideAsync().catch(() => {});
ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.PORTRAIT_UP).catch(() => {});

function Screens() {
  const { ready, session } = useAuth();
  const { colors, scheme } = useTheme();
  const [titleFont] = useTitleFont({ Newsreader_500Medium });
  const [boardFont] = useBoardFont({ BarlowCondensed_700Bold });
  const loaded = ready && titleFont && boardFont;
  useReportAlerts();

  useEffect(() => { if (loaded) SplashScreen.hideAsync().catch(() => {}); }, [loaded]);
  if (!loaded) return null;

  return (
    <>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.page },
        headerStyle: { backgroundColor: colors.tile },
        headerTintColor: colors.ink,
        headerShadowVisible: false,
        headerBackButtonDisplayMode: 'minimal',
      }}>
        <Stack.Protected guard={!session}>
          <Stack.Screen name="sign-in" />
          <Stack.Screen name="sign-in-example" />
        </Stack.Protected>
        <Stack.Protected guard={!!session}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="camera" options={{ presentation: 'fullScreenModal', gestureEnabled: false, animation: 'fade' }} />
          <Stack.Screen name="mark" />
          <Stack.Screen name="report" options={{ headerShown: true, title: 'Report' }} />
          <Stack.Screen name="page" options={{ headerShown: true, title: '' }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}

export default function Root() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Screens />
      </AuthProvider>
    </ThemeProvider>
  );
}
