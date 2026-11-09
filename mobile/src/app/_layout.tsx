import { BarlowCondensed_700Bold, useFonts as useBoardFont } from '@expo-google-fonts/barlow-condensed';
import { Newsreader_500Medium, useFonts as useTitleFont } from '@expo-google-fonts/newsreader';
import { Stack } from 'expo-router';
import * as ScreenOrientation from 'expo-screen-orientation';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { View } from 'react-native';
import { Intro } from '@/components/Intro';
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
  const [intro, setIntro] = useState(true);
  const endIntro = useCallback(() => setIntro(false), []);
  useReportAlerts();

  // The phone's still launch picture hands over to the moving intro as soon as fonts are in.
  useEffect(() => { if (titleFont) SplashScreen.hideAsync().catch(() => {}); }, [titleFont]);
  if (!titleFont) return null;

  return (
    <View style={{ flex: 1, backgroundColor: colors.page }}>
      <StatusBar style={intro || scheme === 'dark' ? 'light' : 'dark'} />
      {loaded && <Stack screenOptions={{
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
      </Stack>}
      {intro && <Intro ready={!!loaded} onDone={endIntro} />}
    </View>
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
