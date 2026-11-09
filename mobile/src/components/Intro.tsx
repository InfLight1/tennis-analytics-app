// The opening moment: the night court draws itself, then the app fades in.
// Runs over the app while it loads underneath. Short on purpose (Rudra, Nov 8).
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, useWindowDimensions } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useDerivedValue, useReducedMotion, useSharedValue, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { CourtScene } from '@/components/CourtScene';
import { court } from '@/lib/theme';

export const INTRO_MS = 1100;
const TOP = 0.26, BOTTOM = 0.74;

const span = (t: number, a: number, b: number) => { 'worklet'; return Math.min(Math.max((t - a) / (b - a), 0), 1); };

export function Intro({ ready, onDone }: { ready: boolean; onDone: () => void }) {
  const { width: W, height: H } = useWindowDimensions();
  const calm = useReducedMotion();
  const t = useSharedValue(0);
  const fade = useSharedValue(1);
  const [played, setPlayed] = useState(false);

  useEffect(() => {
    if (calm) { t.value = 1; return; }
    t.value = withTiming(1, { duration: INTRO_MS, easing: Easing.out(Easing.quad) }, (ok) => { if (ok) scheduleOnRN(setPlayed, true); });
  }, [calm, t]);

  // Leave once the court is drawn and the app underneath is ready.
  useEffect(() => {
    if (!(played || calm) || !ready) return;
    fade.value = withTiming(0, { duration: 260, easing: Easing.out(Easing.quad) }, (ok) => { if (ok) scheduleOnRN(onDone); });
  }, [played, ready, calm, fade, onDone]);

  // A tap jumps to the end.
  const skip = () => { t.set(1); setPlayed(true); };

  const draw = useDerivedValue(() => span(t.value, 0, 1));
  const courtStyle = useAnimatedStyle(() => ({ opacity: span(t.value, 0, 0.2) }));
  const rootStyle = useAnimatedStyle(() => ({ opacity: fade.value }));

  return (
    <Animated.View style={[StyleSheet.absoluteFill, { backgroundColor: court.deep, zIndex: 10 }, rootStyle]} accessibilityLabel="Advantage AI" accessibilityRole="image">
      <Animated.View style={[StyleSheet.absoluteFill, courtStyle]}>
        <CourtScene width={W} height={H} top={TOP} bottom={BOTTOM} draw={draw} />
      </Animated.View>
      <Pressable accessibilityRole="button" accessibilityLabel="Skip intro" onPress={skip} style={StyleSheet.absoluteFill} />
    </Animated.View>
  );
}
