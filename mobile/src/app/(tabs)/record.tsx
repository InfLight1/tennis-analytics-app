import { Paths } from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { getThumbnailAsync } from 'expo-video-thumbnails';
import { useCallback, useEffect, useState } from 'react';
import { Alert, ScrollView, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { startSend } from '../../../modules/advantage-send';
import { SendingList } from '@/components/SendingList';
import { Body, Button, Field, Label, Row, Segments, Tile, Title } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { API_BASE, PART_BYTES } from '@/lib/config';
import { beginMatch, spaceWarning, UNSENT_KEY, type MatchType, type Unsent } from '@/lib/match';
import { store } from '@/lib/store';
import { useTheme } from '@/lib/theme';

const TYPES: { value: MatchType; label: string }[] = [
  { value: 'singles', label: 'Singles' },
  { value: 'doubles', label: 'Doubles' },
];

export default function Record() {
  const { colors } = useTheme();
  const { user, creds, session, passcode } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { pick } = useLocalSearchParams<{ pick?: string }>();
  const [type, setType] = useState<MatchType>('singles');
  const [near, setNear] = useState(user?.role === 'coach' ? '' : user?.name ?? '');
  const [far, setFar] = useState('');
  const [keep, setKeep] = useState(false);
  const [picking, setPicking] = useState(false);
  const [unsent, setUnsent] = useState<Unsent | null>(null);

  const info = { type, near, far };

  useFocusEffect(useCallback(() => {
    store.get(UNSENT_KEY).then((raw) => setUnsent(raw ? JSON.parse(raw) : null));
    store.get('keepInPhotos').then((v) => setKeep(v === '1'));
  }, []));

  const record = async () => {
    const warning = spaceWarning(Paths.availableDiskSpace);
    if (warning?.block) { Alert.alert('Not enough space', warning.text); return; }
    const go = () => router.push({ pathname: '/camera', params: { ...info, keep: keep ? '1' : '0' } });
    const seen = await store.get('dataNoteSeen');
    const notes = [warning?.text, seen ? null : 'A 50-minute match is about 6 GB of mobile data. It sends right after you stop.'].filter(Boolean);
    if (!notes.length) { go(); return; }
    store.set('dataNoteSeen', '1');
    Alert.alert('Before you film', notes.join('\n\n'), [{ text: 'Not now', style: 'cancel' }, { text: 'Continue', onPress: go }]);
  };

  const upload = useCallback(async () => {
    setPicking(true);
    try {
      const picked = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['videos'],
        videoExportPreset: ImagePicker.VideoExportPreset.Passthrough,
        preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Current,
      });
      const video = picked.assets?.[0];
      if (picked.canceled || !video) return;
      const still = await getThumbnailAsync(video.uri, { time: 0, quality: 1 });
      const { job, r2 } = await beginMatch(still.uri, creds, video.fileSize ?? 0);
      router.push({ pathname: '/mark', params: { job, r2: r2 ? '1' : '0', file: video.uri, type, near, far } });
    } catch (e) {
      Alert.alert("Couldn't open that video", e instanceof Error ? e.message : 'Try another one.');
    } finally {
      setPicking(false);
    }
  }, [creds, far, near, router, type]);

  useEffect(() => {
    if (pick !== '1') return;
    router.setParams({ pick: undefined });
    const opening = setTimeout(upload, 0);
    return () => clearTimeout(opening);
  }, [pick, router, upload]);

  const sendUnsent = async () => {
    if (!unsent) return;
    await startSend({ jobId: unsent.job, title: unsent.title, filePath: unsent.path, apiBase: API_BASE, session, passcode, partBytes: PART_BYTES, r2: unsent.r2 })
      .catch((e) => Alert.alert("Couldn't send it", e instanceof Error ? e.message : 'Try again.'));
    store.set(UNSENT_KEY, null);
    setUnsent(null);
  };

  return (
    <ScrollView style={{ backgroundColor: colors.page }} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 16, paddingTop: insets.top + 16, gap: 14 }}>
      <Title>Record a match</Title>
      <SendingList />

      {unsent && (
        <Tile>
          <Title size={22}>Unsent recording</Title>
          <Body muted>{`${unsent.title} stopped before it was sent. What was filmed is on this phone.`}</Body>
          <Button title="Send it now" onPress={sendUnsent} />
          <Row title="Discard it" danger onPress={() => { store.set(UNSENT_KEY, null); setUnsent(null); }} />
        </Tile>
      )}

      <Tile>
        <Segments label="Match type" options={TYPES} value={type} onChange={setType} />
        <Field label={type === 'doubles' ? 'Team at the near end' : 'Player at the near end'} hint="closest to the camera" value={near} onChangeText={setNear} maxLength={40} placeholder={type === 'doubles' ? 'e.g. Alex & Jo' : 'e.g. Alex'} />
        <Field label={type === 'doubles' ? 'Team at the far end' : 'Player at the far end'} value={far} onChangeText={setFar} maxLength={40} placeholder={type === 'doubles' ? 'e.g. Sam & Lee' : 'e.g. Sam'} />
        <Body muted small>A teammate&apos;s name adds the match to their dashboard too.</Body>
      </Tile>

      <Tile night>
        <Label color={colors.onNight2}>New match</Label>
        <Button title="Record match" kind="ball" onPress={record} />
        <Button title="Upload a video" kind="nightLine" onPress={upload} busy={picking} />
        <Body small color={colors.onNight2}>Phone on the back fence, up high, centred on the court.</Body>
      </Tile>

      <Tile>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ flex: 1, gap: 2 }}>
            <Label color={colors.ink}>Keep a copy in Photos</Label>
            <Body muted small>Otherwise the video leaves this phone once it&apos;s safely sent.</Body>
          </View>
          <Switch accessibilityLabel="Keep a copy in Photos" value={keep} onValueChange={(v) => { setKeep(v); store.set('keepInPhotos', v ? '1' : null); }} trackColor={{ true: colors.ball }} />
        </View>
      </Tile>
      <Row title="How to film" onPress={() => router.push({ pathname: '/page', params: { path: '/new#filmGuide' } })} />
    </ScrollView>
  );
}
