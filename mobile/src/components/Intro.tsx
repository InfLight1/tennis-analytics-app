// The opening moment: the night court draws itself, a short rally plays, and the last ball
// flies up to become the logo. Runs over the app while it loads underneath, then fades away.
import * as Haptics from 'expo-haptics';
import { useEffect, useMemo, useState } from 'react';
import { StyleSheet, Text, useWindowDimensions } from 'react-native';
import Animated, { Easing, useAnimatedProps, useAnimatedStyle, useDerivedValue, useReducedMotion, useSharedValue, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { Circle, Ellipse } from 'react-native-svg';
import { BallIcon } from '@/components/icons';
import { CourtScene } from '@/components/CourtScene';
import { ballAt, makeCam, project } from '@/lib/courtView';
import { court, fonts } from '@/lib/theme';

export const INTRO_MS = 2800;
const LOGO = 72;
const TOP = 0.26, BOTTOM = 0.74;
const ACircle = Animated.createAnimatedComponent(Circle);
const AEllipse = Animated.createAnimatedComponent(Ellipse);

const clamp = (v: number) => { 'worklet'; return Math.min(Math.max(v, 0), 1); };
const span = (t: number, a: number, b: number) => { 'worklet'; return clamp((t - a) / (b - a)); };
const ease = (v: number) => { 'worklet'; return v * v * (3 - 2 * v); };

export function Intro({ ready, onDone }: { ready: boolean; onDone: () => void }) {
  const { width: W, height: H } = useWindowDimensions();
  const calm = useReducedMotion();
  const t = useSharedValue(0);
  const fade = useSharedValue(1);
  const [played, setPlayed] = useState(false);
  const cam = useMemo(() => makeCam(W, H, TOP, BOTTOM), [W, H]);
  const logo = useMemo(() => ({ x: W / 2, y: H * 0.42 }), [W, H]);

  useEffect(() => {
    if (calm) { t.value = 1; return; }
    t.value = withTiming(1, { duration: INTRO_MS, easing: Easing.linear }, (ok) => { if (ok) scheduleOnRN(setPlayed, true); });
    const tap = setTimeout(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {}), INTRO_MS * 0.84);
    return () => clearTimeout(tap);
  }, [calm, t]);

  // Leave once the moment has played and the app underneath is ready.
  useEffect(() => {
    if (!(played || calm) || !ready) return;
    fade.value = withTiming(0, { duration: calm ? 200 : 380, easing: Easing.out(Easing.quad) }, (ok) => { if (ok) scheduleOnRN(onDone); });
  }, [played, ready, calm, fade, onDone]);

  const draw = useDerivedValue(() => span(t.value, 0.02, 0.4));

  // Where the ball is: on the court during the rally, then flying up to the logo spot.
  const ball = useDerivedValue(() => {
    const s = span(t.value, 0.3, 0.72), fly = ease(span(t.value, 0.72, 0.86));
    const p = ballAt(s), q = project(cam, p[0], p[1], p[2]), g = project(cam, p[0], p[1], 0);
    const r0 = Math.max(q[2] * 0.2, 3);
    return {
      x: q[0] + (logo.x - q[0]) * fly, y: q[1] + (logo.y - q[1]) * fly, r: r0 + (LOGO * 0.4375 - r0) * fly,
      gx: g[0], gy: g[1], gr: Math.max(g[2] * 0.22, 3), on: span(t.value, 0.3, 0.33), fly,
    };
  });

  const ballProps = useAnimatedProps(() => ({ cx: ball.value.x, cy: ball.value.y, r: ball.value.r, opacity: ball.value.on }));
  const glowProps = useAnimatedProps(() => ({ cx: ball.value.x, cy: ball.value.y, r: ball.value.r * 1.9, opacity: ball.value.on * 0.22 }));
  const shadowProps = useAnimatedProps(() => ({
    cx: ball.value.gx, cy: ball.value.gy, rx: ball.value.gr * 1.2, ry: ball.value.gr * 0.45, opacity: ball.value.on * 0.5 * (1 - ball.value.fly),
  }));

  const courtStyle = useAnimatedStyle(() => ({ opacity: ease(span(t.value, 0, 0.12)) }));
  const dimStyle = useAnimatedStyle(() => ({ opacity: 0.62 * ease(span(t.value, 0.72, 0.9)) }));
  const seamStyle = useAnimatedStyle(() => ({ opacity: span(t.value, 0.84, 0.9) }));
  const wordStyle = useAnimatedStyle(() => {
    const k = ease(span(t.value, 0.84, 0.97));
    return { opacity: k, transform: [{ translateY: 14 * (1 - k) }] };
  });
  const rootStyle = useAnimatedStyle(() => ({ opacity: fade.value }));

  return (
    <Animated.View style={[StyleSheet.absoluteFill, { backgroundColor: court.deep, zIndex: 10 }, rootStyle]} accessibilityLabel="Advantage AI" accessibilityRole="image">
      <Animated.View style={[StyleSheet.absoluteFill, courtStyle]}>
        <CourtScene width={W} height={H} top={TOP} bottom={BOTTOM} draw={draw}>
          <AEllipse fill="#06100C" animatedProps={shadowProps} />
          <ACircle fill="#C6DA2C" animatedProps={glowProps} />
          <ACircle fill="#C6DA2C" animatedProps={ballProps} />
        </CourtScene>
      </Animated.View>
      <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, { backgroundColor: court.deep }, dimStyle]} />
      <Animated.View pointerEvents="none" style={[styles.at, { left: logo.x - LOGO / 2, top: logo.y - LOGO / 2 }, seamStyle]}>
        <BallIcon size={LOGO} />
      </Animated.View>
      <Animated.View pointerEvents="none" style={[styles.words, { top: logo.y + LOGO / 2 + 18 }, wordStyle]}>
        <Text style={styles.name}>Advantage AI</Text>
        <Text style={styles.tag}>Film your match. Get your top fixes.</Text>
      </Animated.View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  at: { position: 'absolute', width: LOGO, height: LOGO },
  words: { position: 'absolute', left: 0, right: 0, alignItems: 'center', gap: 6 },
  name: { fontFamily: fonts.title, fontSize: 38, lineHeight: 44, letterSpacing: -0.4, color: '#F2F5F1' },
  tag: { fontSize: 16, lineHeight: 22, color: '#B9C4BD' },
});
