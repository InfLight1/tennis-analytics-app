import { useFocusEffect, useLocalSearchParams } from 'expo-router';
import * as ScreenOrientation from 'expo-screen-orientation';
import { useCallback } from 'react';
import { PageView } from '@/components/PageView';

export default function Report() {
  const { job, watch } = useLocalSearchParams<{ job: string; watch?: string }>();

  // Clips can go full screen sideways; the rest of the app stays upright.
  useFocusEffect(useCallback(() => {
    ScreenOrientation.unlockAsync().catch(() => {});
    return () => { ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.PORTRAIT_UP).catch(() => {}); };
  }, []));

  return <PageView path={`/report?job=${encodeURIComponent(job)}${watch === '1' ? '&watch=1' : ''}`} />;
}
