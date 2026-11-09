import type { ColorValue } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';

type P = { color: ColorValue; size?: number };
const line = { fill: 'none', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' } as const;

export const HomeIcon = ({ color, size = 24 }: P) => <Svg width={size} height={size} viewBox="0 0 24 24"><Path d="M4 11l8-6 8 6v9H4z" stroke={color} {...line} /></Svg>;
export const ListIcon = ({ color, size = 24 }: P) => <Svg width={size} height={size} viewBox="0 0 24 24"><Path d="M5 6h14M5 12h14M5 18h9" stroke={color} {...line} /></Svg>;
export const PersonIcon = ({ color, size = 24 }: P) => <Svg width={size} height={size} viewBox="0 0 24 24"><Circle cx={12} cy={9} r={3.5} stroke={color} {...line} /><Path d="M5 20c1.5-4 12.5-4 14 0" stroke={color} {...line} /></Svg>;
export const EyeIcon = ({ color, size = 24 }: P) => <Svg width={size} height={size} viewBox="0 0 24 24"><Path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" stroke={color} {...line} /><Circle cx={12} cy={12} r={3} stroke={color} {...line} /></Svg>;
export const EyeOffIcon = ({ color, size = 24 }: P) => <Svg width={size} height={size} viewBox="0 0 24 24"><Path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" stroke={color} {...line} /><Circle cx={12} cy={12} r={3} stroke={color} {...line} /><Path d="M4 4l16 16" stroke={color} {...line} /></Svg>;
export const BallIcon = ({ size = 26 }: { size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 32 32">
    <Circle cx={16} cy={16} r={14} fill="#C6DA2C" />
    <Path d="M5 8c6 4 6 12 0 16M27 8c-6 4-6 12 0 16" fill="none" stroke="#0F1A14" strokeWidth={1.8} strokeLinecap="round" />
  </Svg>
);
