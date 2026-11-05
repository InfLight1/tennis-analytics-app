// The Court look's building blocks for the app's native screens.
import * as Haptics from 'expo-haptics';
import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps, type ViewStyle } from 'react-native';
import { fonts, radius, useTheme } from '@/lib/theme';

export function Title({ children, size = 30, color }: { children: ReactNode; size?: number; color?: string }) {
  const { colors } = useTheme();
  return <Text accessibilityRole="header" style={{ fontFamily: fonts.title, fontSize: size, lineHeight: size * 1.12, letterSpacing: -0.3, color: color ?? colors.ink }}>{children}</Text>;
}

export function Body({ children, muted, small, color, center }: { children: ReactNode; muted?: boolean; small?: boolean; color?: string; center?: boolean }) {
  const { colors } = useTheme();
  return <Text style={{ fontSize: small ? 14 : 16, lineHeight: small ? 19 : 22, color: color ?? (muted ? colors.ink2 : colors.ink), textAlign: center ? 'center' : 'left' }}>{children}</Text>;
}

export function Label({ children, color }: { children: ReactNode; color?: string }) {
  const { colors } = useTheme();
  return <Text style={{ fontSize: 14, fontWeight: '600', color: color ?? colors.ink2 }}>{children}</Text>;
}

export function Tile({ children, night, style }: { children: ReactNode; night?: boolean; style?: ViewStyle }) {
  const { colors } = useTheme();
  return (
    <View style={[{ backgroundColor: night ? colors.night : colors.tile, borderColor: night ? colors.night : colors.line, borderWidth: 1, borderRadius: radius.tile, padding: 18, gap: 10 }, style]}>
      {children}
    </View>
  );
}

type ButtonKind = 'ball' | 'ink' | 'line' | 'nightLine' | 'danger';

export function Button({ title, onPress, kind = 'ink', busy, disabled }: { title: string; onPress: () => void; kind?: ButtonKind; busy?: boolean; disabled?: boolean }) {
  const { colors } = useTheme();
  const look = {
    ball: { bg: colors.ball, fg: colors.ballInk, border: colors.ball },
    ink: { bg: colors.ink, fg: colors.page, border: colors.ink },
    line: { bg: 'transparent', fg: colors.ink, border: colors.line2 },
    nightLine: { bg: 'transparent', fg: colors.onNight, border: colors.onNight2 },
    danger: { bg: 'transparent', fg: colors.lost, border: colors.lost },
  }[kind];
  const off = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      disabled={off}
      onPress={() => { Haptics.selectionAsync().catch(() => {}); onPress(); }}
      style={({ pressed }) => [styles.button, kind === 'ball' && styles.big, { backgroundColor: look.bg, borderColor: look.border, opacity: off ? 0.5 : 1, transform: [{ scale: pressed ? 0.98 : 1 }] }]}
    >
      {busy ? <ActivityIndicator color={look.fg} /> : <Text style={{ color: look.fg, fontSize: kind === 'ball' ? 18 : 16, fontWeight: '600' }}>{title}</Text>}
    </Pressable>
  );
}

export function Field({ label, hint, ...input }: TextInputProps & { label: string; hint?: string }) {
  const { colors, scheme } = useTheme();
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ fontSize: 15, fontWeight: '600', color: colors.ink }}>{label}{hint ? <Text style={{ fontWeight: '400', color: colors.ink2 }}>{`  ${hint}`}</Text> : null}</Text>
      <TextInput
        accessibilityLabel={label}
        keyboardAppearance={scheme}
        placeholderTextColor={colors.ink3}
        {...input}
        style={{ minHeight: 48, borderRadius: radius.box, borderWidth: 1, borderColor: colors.line2, backgroundColor: colors.tile2, color: colors.ink, paddingHorizontal: 12, fontSize: 16 }}
      />
    </View>
  );
}

export function Segments<T extends string>({ options, value, onChange, label }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={{ flexDirection: 'row', backgroundColor: colors.tile2, borderColor: colors.line, borderWidth: 1, borderRadius: radius.pill, padding: 3 }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable key={o.value} accessibilityRole="radio" accessibilityState={{ checked: on }} onPress={() => onChange(o.value)}
            style={{ flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radius.pill, backgroundColor: on ? colors.ink : 'transparent' }}>
            <Text style={{ fontSize: 15, fontWeight: '600', color: on ? colors.page : colors.ink }}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Row({ title, onPress, danger }: { title: string; onPress: () => void; danger?: boolean }) {
  const { colors } = useTheme();
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => ({ minHeight: 48, justifyContent: 'center', opacity: pressed ? 0.6 : 1 })}>
      <Text style={{ fontSize: 16, fontWeight: '600', color: danger ? colors.lost : colors.ink }}>{title}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { minHeight: 50, borderRadius: radius.pill, borderWidth: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 22 },
  big: { minHeight: 58 },
});
