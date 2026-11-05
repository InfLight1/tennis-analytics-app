import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback } from 'react';
import { Alert } from 'react-native';
import { startSend } from '../../modules/advantage-send';
import { PageView } from '@/components/PageView';
import { askForAlerts } from '@/lib/alerts';
import { useAuth } from '@/lib/auth';
import { API_BASE, PART_BYTES } from '@/lib/config';
import { markPath, matchTitle, type MatchType } from '@/lib/match';
import type { PageMessage } from '@/lib/pages';

// An uploaded video: mark the court on its first picture, then it sends in the background.
export default function Mark() {
  const p = useLocalSearchParams<{ job: string; r2: string; file: string; type: MatchType; near: string; far: string }>();
  const { creds, session, passcode } = useAuth();
  const router = useRouter();
  const info = { type: p.type, near: p.near, far: p.far };

  const onMessage = useCallback((m: PageMessage) => {
    if (m.type !== 'marked') return;
    startSend({ jobId: p.job, title: matchTitle({ type: p.type, near: p.near, far: p.far }), filePath: p.file, apiBase: API_BASE, session, passcode, partBytes: PART_BYTES, r2: p.r2 === '1' })
      .then(() => askForAlerts(creds).catch(() => {}))
      .catch((e) => Alert.alert("Couldn't send it", e instanceof Error ? e.message : 'Try again.'))
      .finally(() => router.back());
  }, [creds, p.far, p.file, p.job, p.near, p.r2, p.type, passcode, router, session]);

  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Mark the court' }} />
      <PageView path={markPath(p.job, info, false)} onMessage={onMessage} />
    </>
  );
}
