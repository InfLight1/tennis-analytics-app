// The drawn night court from the back fence. Still on the sign-in band; lines draw themselves in the intro.
import { useMemo } from 'react';
import Animated, { useAnimatedProps, type SharedValue } from 'react-native-reanimated';
import Svg, { Defs, Path, RadialGradient, Rect, Stop } from 'react-native-svg';
import { HL, HW, LINES, linePath, makeCam, polyPath, project } from '@/lib/courtView';
import { court } from '@/lib/theme';

const APath = Animated.createAnimatedComponent(Path);

type Props = { width: number; height: number; top?: number; bottom?: number; draw?: SharedValue<number>; children?: React.ReactNode };

export function CourtScene({ width, height, top = 0.3, bottom = 0.78, draw, children }: Props) {
  const cam = useMemo(() => makeCam(width, height, top, bottom), [width, height, top, bottom]);
  const shapes = useMemo(() => {
    const centre = project(cam, 0, 0);
    return {
      surround: polyPath(cam, [[-11, -HL - 3], [11, -HL - 3], [11, 20], [-11, 20]]),
      inside: polyPath(cam, [[-HW, -HL], [HW, -HL], [HW, HL], [-HW, HL]]),
      net: polyPath(cam, [[-6.4, 0, 0], [6.4, 0, 0], [6.4, 0, 1.07], [0, 0, 0.914], [-6.4, 0, 1.07]]),
      netTop: `M${project(cam, -6.4, 0, 1.07).slice(0, 2).join(' ')} L${project(cam, 0, 0, 0.914).slice(0, 2).join(' ')} L${project(cam, 6.4, 0, 1.07).slice(0, 2).join(' ')}`,
      lines: LINES.map((l) => linePath(cam, l)),
      glow: { x: centre[0], y: centre[1], r: Math.max(width, height) * 0.62 },
    };
  }, [cam, width, height]);

  return (
    <Svg width={width} height={height}>
      <Defs>
        <RadialGradient id="light" cx={shapes.glow.x} cy={shapes.glow.y} r={shapes.glow.r} gradientUnits="userSpaceOnUse">
          <Stop offset="0" stopColor="#ECFFD6" stopOpacity={0.22} />
          <Stop offset="1" stopColor="#ECFFD6" stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Rect width={width} height={height} fill={court.deep} />
      <Path d={shapes.surround} fill={court.out} />
      <Path d={shapes.inside} fill={court.inn} />
      <Rect width={width} height={height} fill="url(#light)" />
      {shapes.lines.map((l, i) => <CourtLine key={i} d={l.d} len={l.len} i={i} draw={draw} width={Math.max(1.5, width / 220)} />)}
      <Path d={shapes.net} fill="#0A1410" fillOpacity={0.45} />
      <Path d={shapes.netTop} stroke="#FFFFFF" strokeWidth={Math.max(2, width / 180)} fill="none" strokeLinecap="round" />
      {children}
    </Svg>
  );
}

function CourtLine({ d, len, i, draw, width }: { d: string; len: number; i: number; draw?: SharedValue<number>; width: number }) {
  const props = useAnimatedProps(() => {
    if (!draw) return { strokeDashoffset: 0 };
    const start = i * 0.05, t = Math.min(Math.max((draw.value - start) / 0.45, 0), 1);
    const eased = t * t * (3 - 2 * t);
    return { strokeDashoffset: len * (1 - eased) };
  });
  return <APath d={d} stroke={court.line} strokeWidth={width} strokeLinecap="round" strokeDasharray={[len + 1, len + 1]} animatedProps={props} />;
}
