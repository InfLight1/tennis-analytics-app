import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { KeyboardAvoidingView, Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { CourtScene } from '@/components/CourtScene';
import { BallIcon } from '@/components/icons';
import { Body, Button, Field, Label, Row, Segments, Title } from '@/components/ui';
import { useAuth, type SignUp } from '@/lib/auth';
import { radius, useTheme } from '@/lib/theme';

type Mode = 'login' | 'signup';
type Who = 'join' | 'solo' | 'coach';
type Kind = SignUp['kind'];

const MODES: { value: Mode; label: string }[] = [
  { value: 'login', label: 'Log in' },
  { value: 'signup', label: 'Sign up' },
];
const WHO: { value: Who; title: string; line: string }[] = [
  { value: 'join', title: 'Player on a team', line: 'I have a team code from my coach.' },
  { value: 'solo', title: 'Player on my own', line: 'No team yet. I can join one later.' },
  { value: 'coach', title: 'Coach', line: 'Start a team and get a code for players.' },
];
const ACTION: Record<Kind, string> = { signin: 'Log in', join: 'Sign up and join team', solo: 'Sign up', coach: 'Sign up and create team' };
const CLOSED_TEST = "Advantage AI is in a closed test, so you'll need the passcode you were given.";
const BAND = 250;

export default function SignIn() {
  const { colors } = useTheme();
  const { enter } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [mode, setMode] = useState<Mode>('login');
  const [who, setWho] = useState<Who>('join');
  const [f, setF] = useState({ username: '', password: '', code: '', name: '', email: '', passcode: '', team_name: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = (key: keyof typeof f) => (value: string) => setF((old) => ({ ...old, [key]: value }));
  const kind: Kind = mode === 'login' ? 'signin' : who;
  const switchTo = (m: Mode) => { setMode(m); setError(''); };

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      await enter(formFor(kind, f));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  const band = BAND + insets.top;

  return (
    <KeyboardAvoidingView behavior="padding" style={{ flex: 1, backgroundColor: colors.page }}>
      <StatusBar style="light" />
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}>
        <View style={{ height: band }}>
          <CourtScene width={width} height={band} top={0.5} bottom={1.5} />
          <View style={{ position: 'absolute', left: 20, right: 20, top: insets.top + 22, gap: 6 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <BallIcon size={34} />
              <Title size={28} color={colors.onNight}>Advantage AI</Title>
            </View>
            <Body color={colors.onNight2}>Film your match. Get your top fixes.</Body>
          </View>
        </View>

        <View style={{ marginTop: -28, marginHorizontal: 12, padding: 18, gap: 14, backgroundColor: colors.tile, borderColor: colors.line, borderWidth: 1, borderRadius: radius.tile }}>
          <Segments label="Log in or sign up" options={MODES} value={mode} onChange={switchTo} />

          <View style={{ gap: 4, marginTop: 4 }}>
            <Title size={26}>{mode === 'login' ? 'Welcome back' : 'Create your account'}</Title>
            <Body muted>{mode === 'login' ? 'Log in to your account.' : 'New to Advantage AI? Pick who you are.'}</Body>
          </View>

          {mode === 'signup' && (
            <View accessibilityRole="radiogroup" accessibilityLabel="Who is signing up" style={{ gap: 8 }}>
              {WHO.map((o) => <Choice key={o.value} title={o.title} line={o.line} on={who === o.value} onPress={() => { setWho(o.value); setError(''); }} />)}
            </View>
          )}

          {kind === 'join' && <Field label="Team code" hint="6 letters, from your coach" value={f.code} onChangeText={set('code')} autoCapitalize="characters" maxLength={6} autoCorrect={false} />}
          {kind === 'coach' && <Field label="Team name" placeholder="e.g. Varsity Boys" value={f.team_name} onChangeText={set('team_name')} maxLength={60} />}
          {kind !== 'signin' && <Field label="Your name" hint={kind === 'solo' ? 'use this name when you film' : undefined} value={f.name} onChangeText={set('name')} maxLength={40} textContentType="name" autoComplete="name" />}
          <Field label="Username" hint={kind === 'signin' ? undefined : '3-24 letters or numbers'} value={f.username} onChangeText={set('username')} autoCapitalize="none" autoCorrect={false} textContentType="username" autoComplete="username" />
          <Field label="Password" hint={kind === 'signin' ? undefined : 'at least 8 characters'} value={f.password} onChangeText={set('password')} secureTextEntry textContentType={kind === 'signin' ? 'password' : 'newPassword'} autoComplete={kind === 'signin' ? 'current-password' : 'new-password'} />
          {kind === 'solo' && <Field label="Email" hint="optional, for password resets" value={f.email} onChangeText={set('email')} keyboardType="email-address" autoCapitalize="none" autoComplete="email" maxLength={120} />}
          {(kind === 'solo' || kind === 'coach') && (
            <>
              <Field label="Passcode" value={f.passcode} onChangeText={set('passcode')} secureTextEntry autoCapitalize="none" />
              <Body muted small>{CLOSED_TEST}</Body>
            </>
          )}

          {!!error && <View accessibilityLiveRegion="polite"><Body color={colors.lost}>{error}</Body></View>}
          <Button title={ACTION[kind]} onPress={submit} busy={busy} kind="ball" />
          {mode === 'login' && <Body muted small>Forgot your password? Your coach can set a new one for you.</Body>}
          <Pressable accessibilityRole="button" onPress={() => switchTo(mode === 'login' ? 'signup' : 'login')} style={({ pressed }) => ({ minHeight: 44, justifyContent: 'center', opacity: pressed ? 0.6 : 1 })}>
            <Text style={{ fontSize: 16, color: colors.ink2, textAlign: 'center' }}>
              {mode === 'login' ? 'New here? ' : 'Already have an account? '}
              <Text style={{ fontWeight: '600', color: colors.ink, textDecorationLine: 'underline' }}>{mode === 'login' ? 'Sign up' : 'Log in'}</Text>
            </Text>
          </Pressable>
        </View>

        <View style={{ paddingHorizontal: 24, marginTop: 8 }}>
          <Row title="See an example report" onPress={() => router.push('/sign-in-example')} />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Choice({ title, line, on, onPress }: { title: string; line: string; on: boolean; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable accessibilityRole="radio" accessibilityState={{ checked: on }} accessibilityLabel={`${title}. ${line}`} onPress={onPress}
      style={({ pressed }) => ({
        flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, minHeight: 64, borderRadius: radius.box, borderWidth: on ? 2 : 1,
        borderColor: on ? colors.ink : colors.line2, backgroundColor: on ? colors.ballSoft : colors.tile2, transform: [{ scale: pressed ? 0.98 : 1 }],
      })}>
      <View style={{ width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: on ? colors.ink : colors.line2, alignItems: 'center', justifyContent: 'center' }}>
        {on && <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: colors.ink }} />}
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Label color={colors.ink}>{title}</Label>
        <Body muted small>{line}</Body>
      </View>
    </Pressable>
  );
}

type Form = { username: string; password: string; code: string; name: string; email: string; passcode: string; team_name: string };

function formFor(kind: Kind, f: Form): SignUp {
  const { username, password, code, name, email, passcode, team_name } = f;
  if (kind === 'join') return { kind, code, name, username, password };
  if (kind === 'solo') return { kind, name, username, password, email, passcode };
  if (kind === 'coach') return { kind, team_name, name, username, password, passcode };
  return { kind, username, password };
}
