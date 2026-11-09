import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Body, Button, Field, Label, Row, Segments, Tile, Title } from '@/components/ui';
import { apiPost } from '@/lib/api';
import { useVersionLine } from '@/lib/appUpdates';
import { useAuth } from '@/lib/auth';
import { fonts, useTheme, type Appearance_ } from '@/lib/theme';

const LOOKS: { value: Appearance_; label: string }[] = [
  { value: 'auto', label: 'Automatic' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

export default function Account() {
  const { colors, choice, setChoice } = useTheme();
  const { user, team, creds, refresh, signOut, deleteAccount } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [code, setCode] = useState('');
  const [joining, setJoining] = useState(false);
  const [note, setNote] = useState('');
  const version = useVersionLine();
  const coach = user?.role === 'coach';
  const solo = !coach && !user?.team_id;

  const join = async () => {
    setJoining(true);
    setNote('');
    try {
      await apiPost('/api/me/join-team', { code }, creds);
      await refresh();
      setCode('');
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Couldn't join the team.");
    } finally {
      setJoining(false);
    }
  };

  const confirmDelete = () => Alert.alert(
    'Delete your account?',
    "This deletes your account and the reports and videos you filmed, for good. A match with a teammate in it stays for them. You can't undo this.",
    [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete my account',
        style: 'destructive',
        onPress: () => { deleteAccount().catch((e) => Alert.alert("Couldn't delete it", e instanceof Error ? e.message : 'Try again in a moment.')); },
      },
    ],
  );

  const open = (path: string) => router.push({ pathname: '/page', params: { path } });

  return (
    <ScrollView style={{ backgroundColor: colors.page }} contentContainerStyle={{ padding: 16, paddingTop: insets.top + 16, gap: 14 }}>
      <View style={{ gap: 2 }}>
        <Title>{user?.name ?? 'Account'}</Title>
        <Body muted>
          {coach ? `Coach of ${team?.name ?? 'your team'}` : solo ? 'Solo player' : `Player on ${team?.name ?? 'your team'}`}
          {user ? ` · ${user.username}` : ''}
        </Body>
      </View>

      {coach && !!team?.code && (
        <Tile night>
          <Label color={colors.onNight2}>Add players</Label>
          <Text selectable style={{ fontFamily: fonts.board, fontSize: 42, letterSpacing: 2, color: colors.ball }}>{team.code}</Text>
          <Body small color={colors.onNight2}>Players join with this team code.</Body>
        </Tile>
      )}

      {solo && (
        <Tile>
          <Title size={22}>Join a team</Title>
          <Body muted>Got a team code from your coach? Your matches come with you.</Body>
          <Field label="Team code" value={code} onChangeText={setCode} autoCapitalize="characters" maxLength={6} autoCorrect={false} />
          {!!note && <Body color={colors.lost}>{note}</Body>}
          <Button title="Join team" onPress={join} busy={joining} disabled={code.length < 6} />
        </Tile>
      )}

      <Tile>
        <Title size={22}>Appearance</Title>
        <Segments label="Appearance" options={LOOKS} value={choice} onChange={setChoice} />
        <Body muted small>Automatic follows your phone&apos;s light or dark setting.</Body>
      </Tile>

      <Tile style={{ gap: 0 }}>
        <Row title="How to film" onPress={() => open('/new#filmGuide')} />
        <Row title="See an example report" onPress={() => open('/example')} />
        <Row title="Privacy" onPress={() => open('/privacy')} />
      </Tile>

      <Tile style={{ gap: 0 }}>
        <Row title="Sign out" onPress={signOut} />
        <Row title="Delete account" danger onPress={confirmDelete} />
        <Body muted small>{version}</Body>
      </Tile>
    </ScrollView>
  );
}
