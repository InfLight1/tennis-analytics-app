import { useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { BallIcon } from '@/components/icons';
import { Body, Button, Field, Row, Segments, Title } from '@/components/ui';
import { useAuth, type SignUp } from '@/lib/auth';
import { useTheme } from '@/lib/theme';

type Kind = SignUp['kind'];
const CHOICES: { value: Kind; label: string }[] = [
  { value: 'signin', label: 'Sign in' },
  { value: 'join', label: 'My team' },
  { value: 'solo', label: 'Just me' },
  { value: 'coach', label: 'Coach' },
];
const ACTION: Record<Kind, string> = { signin: 'Sign in', join: 'Join team', solo: 'Create my account', coach: 'Create team' };
const CLOSED_TEST = "Advantage AI is in a closed test, so you'll need the passcode you were given.";

export default function SignIn() {
  const { colors } = useTheme();
  const { enter } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [kind, setKind] = useState<Kind>('signin');
  const [f, setF] = useState({ username: '', password: '', code: '', name: '', email: '', passcode: '', team_name: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = (key: keyof typeof f) => (value: string) => setF((old) => ({ ...old, [key]: value }));

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

  return (
    <KeyboardAvoidingView behavior="padding" style={{ flex: 1, backgroundColor: colors.page }}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 16, paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24, gap: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <BallIcon size={36} />
          <Title size={26}>Advantage AI</Title>
        </View>
        <Body muted>Film your match. Get your top fixes.</Body>
        <Segments label="How you want to get in" options={CHOICES} value={kind} onChange={(k) => { setKind(k); setError(''); }} />

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
        <Button title={ACTION[kind]} onPress={submit} busy={busy} />
        {kind === 'signin' && <Body muted small>Forgot your password? Your coach can set a new one for you.</Body>}
        <Row title="See an example report" onPress={() => router.push('/sign-in-example')} />
      </ScrollView>
    </KeyboardAvoidingView>
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
