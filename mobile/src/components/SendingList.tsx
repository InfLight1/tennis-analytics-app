// Matches on their way to a report: on the Record tab, and floating over the Dashboard.
import { useRouter } from 'expo-router';
import { Pressable, Text, View } from 'react-native';
import { sendLine, sendShare, useSends, type Tracked } from '@/lib/sends';
import { radius, useTheme } from '@/lib/theme';
import { Body, Label } from './ui';

function Card({ send, onDismiss }: { send: Tracked; onDismiss: () => void }) {
  const { colors } = useTheme();
  const router = useRouter();
  const stuck = send.phase === 'failed' || !!send.serverProblem;
  const moving = send.phase === 'sending' || send.phase === 'finishing';
  const line = send.reportReady ? 'Your report is ready.' : send.serverProblem || sendLine(send);
  const open = () => { router.push({ pathname: '/report', params: { job: send.jobId } }); onDismiss(); };

  return (
    <Pressable
      accessibilityRole={send.reportReady ? 'button' : undefined}
      disabled={!send.reportReady}
      onPress={open}
      style={{ backgroundColor: colors.tile, borderColor: colors.line, borderWidth: 1, borderRadius: radius.box, padding: 12, gap: 6 }}
    >
      <Label color={colors.ink}>{send.title}</Label>
      <Body small muted={!stuck} color={stuck ? colors.lost : undefined}>{line}</Body>
      {moving && (
        <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(sendShare(send) * 100) }} style={{ height: 6, borderRadius: 3, backgroundColor: colors.tile2, overflow: 'hidden' }}>
          <View style={{ height: 6, width: `${Math.round(sendShare(send) * 100)}%`, backgroundColor: colors.ball }} />
        </View>
      )}
      {(stuck || send.reportReady) && (
        <Pressable accessibilityRole="button" onPress={onDismiss} hitSlop={8} style={{ alignSelf: 'flex-start', minHeight: 32, justifyContent: 'center' }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.ink2 }}>Dismiss</Text>
        </Pressable>
      )}
    </Pressable>
  );
}

export function SendingList({ floating }: { floating?: boolean }) {
  const { sends, dismiss } = useSends();
  if (!sends.length) return null;
  return (
    <View pointerEvents="box-none" style={floating ? { position: 'absolute', left: 12, right: 12, bottom: 12, gap: 8 } : { gap: 8 }}>
      {sends.map((s) => <Card key={s.jobId} send={s} onDismiss={() => dismiss(s.jobId)} />)}
    </View>
  );
}
