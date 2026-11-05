// Filming a match: the iPhone camera at 4K, hands-free aiming, then Stop and it sends by itself.
import * as Brightness from 'expo-brightness';
import { File, Paths } from 'expo-file-system';
import { useKeepAwake } from 'expo-keep-awake';
import * as MediaLibrary from 'expo-media-library/legacy';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as ScreenOrientation from 'expo-screen-orientation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import {
  Camera, CommonResolutions, useCameraDevice, useCameraPermission, useMicrophonePermission, usePhotoOutput, useVideoOutput, type Recorder,
} from 'react-native-vision-camera';
import { startSend } from '../../modules/advantage-send';
import { PageView } from '@/components/PageView';
import { Body, Button, Title } from '@/components/ui';
import { askForAlerts } from '@/lib/alerts';
import { apiPostPicture } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { API_BASE, MAX_RECORDING_MINUTES, PART_BYTES, VIDEO_BIT_RATE, WARN_RECORDING_MINUTES } from '@/lib/config';
import { aimStep, clock, COUNTDOWN, LINES, startAim, type AimAnswer } from '@/lib/handsFree';
import { beginMatch, markPath, matchTitle, UNSENT_KEY, type MatchType } from '@/lib/match';
import type { PageMessage } from '@/lib/pages';
import { store } from '@/lib/store';
import { palettes } from '@/lib/theme';
import { prepareVoice, say, stopVoice } from '@/lib/voice';

// Recording is always dark, in both light and dark mode.
const c = palettes.dark;
const VIDEO_W = 3840, VIDEO_H = 2160, AIM_W = 1280, AIM_H = 720;
const wait = (ms: number, run: { stop: boolean }) => new Promise<void>((done) => {
  const started = Date.now();
  const tick = () => (run.stop || Date.now() - started >= ms ? done() : setTimeout(tick, 100));
  tick();
});

type Phase = 'aim' | 'handsfree' | 'marking' | 'ready' | 'countdown' | 'recording' | 'stopping' | 'stopped';

export default function CameraScreen() {
  useKeepAwake();
  const p = useLocalSearchParams<{ type: MatchType; near: string; far: string; keep: string }>();
  const router = useRouter();
  const { creds, session, passcode } = useAuth();
  const [doubles, setDoubles] = useState(p.type === 'doubles');
  const info = { type: (doubles ? 'doubles' : 'singles') as MatchType, near: p.near, far: p.far };

  const device = useCameraDevice('back');
  const camera = useCameraPermission();
  const microphone = useMicrophonePermission();
  const video = useVideoOutput({ targetResolution: CommonResolutions.UHD_16_9, enableAudio: true, targetBitRate: VIDEO_BIT_RATE, fileType: 'mov' });
  const photo = usePhotoOutput({ targetResolution: CommonResolutions.UHD_16_9, containerFormat: 'jpeg', quality: 0.9, qualityPrioritization: 'speed' });

  const [phase, setPhase] = useState<Phase>('aim');
  const [tip, setTip] = useState('');
  const [problem, setProblem] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [showPicture, setShowPicture] = useState(false);
  const [match, setMatch] = useState<{ job: string; r2: boolean } | null>(null);
  const [auto, setAuto] = useState(false);
  const run = useRef({ stop: false });
  const recorder = useRef<Recorder | null>(null);
  const startedAt = useRef(0);
  const screenLevel = useRef<number | null>(null);
  const finished = useRef(false);

  const speak = useCallback((line: string) => { setTip(line); say(line); }, []);

  useEffect(() => {
    ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.LANDSCAPE).catch(() => {});
    prepareVoice();
    if (!camera.hasPermission) camera.requestPermission();
    if (!microphone.hasPermission) microphone.requestPermission();
    const stopRun = run.current;
    return () => {
      stopRun.stop = true;
      stopVoice();
      if (screenLevel.current != null) Brightness.setBrightnessAsync(screenLevel.current).catch(() => {});
      ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.PORTRAIT_UP).catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- asks once when the screen opens
  }, []);

  useEffect(() => {
    if (phase !== 'recording') return;
    const timer = setInterval(() => setElapsed(Date.now() - startedAt.current), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  const picture = useCallback(async (width: number, height: number, quality: number) => {
    const shot = await photo.capturePhoto({ enableShutterSound: false }, {});
    try {
      const image = await shot.toImageAsync();
      const sized = await image.resizeAsync(width, height);
      return `file://${await sized.saveToTemporaryFileAsync('jpg', quality)}`;
    } finally {
      shot.dispose();
    }
  }, [photo]);

  // The marking picture is the same size as the video, so the court lines match it exactly.
  const startMarking = useCallback(async (hands: boolean) => {
    setProblem('');
    try {
      const still = await picture(VIDEO_W, VIDEO_H, 90);
      setMatch(await beginMatch(still, creds));
      setAuto(hands);
      setPhase('marking');
    } catch (e) {
      setProblem(`Couldn't get ready: ${e instanceof Error ? e.message : 'check the signal'}. Try again.`);
      setPhase('aim');
      if (hands) speak(LINES.wrong);
    }
  }, [creds, picture, speak]);

  const handsFree = useCallback(async () => {
    run.current = { stop: false };
    const me = run.current;
    setPhase('handsfree');
    speak(LINES.intro);
    await wait(6000, me);
    let state = startAim(doubles);
    while (!me.stop) {
      let answer: AimAnswer | null = null;
      try {
        const shot = await picture(AIM_W, AIM_H, 85);
        answer = await apiPostPicture<AimAnswer>('/api/aim', shot, { doubles: state.doubles ? '1' : '0' }, creds);
      } catch { /* weak signal: tries again */ }
      if (me.stop) return;
      const next = aimStep(state, answer, Date.now());
      state = next.state;
      if (next.step.next === 'mark') break;
      if (next.step.next === 'doubles') setDoubles(true);
      if (next.step.say) speak(next.step.say);
      await wait(next.step.waitMs, me);
    }
    if (me.stop) return;
    speak(LINES.marking(state.doubles));
    await startMarking(true);
  }, [creds, doubles, picture, speak, startMarking]);

  const finish = useCallback(async (path: string) => {
    if (finished.current || !match) return;
    finished.current = true;
    setPhase('stopped');
    if (screenLevel.current != null) Brightness.setBrightnessAsync(screenLevel.current).catch(() => {});
    if (p.keep === '1') {
      const allowed = await MediaLibrary.requestPermissionsAsync(true).catch(() => null);
      if (allowed?.granted) await MediaLibrary.saveToLibraryAsync(path).catch(() => {});
    }
    try {
      await startSend({ jobId: match.job, title: matchTitle(info), filePath: path, apiBase: API_BASE, session, passcode, partBytes: PART_BYTES, r2: match.r2 });
      store.set(UNSENT_KEY, null);
      askForAlerts(creds).catch(() => {});
    } catch (e) {
      Alert.alert("Couldn't start sending", `${e instanceof Error ? e.message : 'Try again.'} Your video is safe: it's on the Record tab.`);
    }
    router.back();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- info is rebuilt each render from the values listed
  }, [creds, doubles, match, p.far, p.keep, p.near, passcode, router, session]);

  const record = useCallback(async () => {
    if (!match) return;
    setProblem('');
    try {
      const r = await video.createRecorder({ filePath: `${new File(Paths.document, `${match.job}.mov`).uri.replace('file://', '')}`, maxDuration: MAX_RECORDING_MINUTES * 60 });
      recorder.current = r;
      store.set(UNSENT_KEY, JSON.stringify({ job: match.job, r2: match.r2, path: r.filePath, title: matchTitle(info) }));
      await r.startRecording(
        (path) => { finish(path); },
        (error) => {
          // A call or the app being left stops the camera. Whatever was filmed is kept.
          if (new File(`file://${r.filePath}`).exists) { finish(r.filePath); return; }
          setProblem(`The recording stopped: ${error.message}`);
          setPhase('ready');
        },
      );
      startedAt.current = Date.now();
      setPhase('recording');
      setShowPicture(false);
      Brightness.getBrightnessAsync().then((level) => {
        screenLevel.current = level;
        return Brightness.setBrightnessAsync(0.05);
      }).catch(() => {});
    } catch (e) {
      setProblem(`The camera didn't start: ${e instanceof Error ? e.message : 'try again'}.`);
      setPhase('ready');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- info is rebuilt each render from the values listed
  }, [doubles, finish, match, p.far, p.near, video]);

  const countdown = useCallback(async () => {
    const me = run.current;
    setPhase('countdown');
    for (const [line, ms] of COUNTDOWN) {
      if (me.stop) return;
      speak(line);
      await wait(ms, me);
    }
    if (me.stop) return;
    await record();
    speak(LINES.recording);
  }, [record, speak]);

  const onPage = useCallback((m: PageMessage) => {
    if (m.type === 'marked') {
      if (auto) countdown();
      else setPhase('ready');
    }
    if (m.type === 'mark-check') {
      setAuto(false);
      speak(LINES.check);
    }
  }, [auto, countdown, speak]);

  const stop = () => Alert.alert('Stop recording?', 'This ends the match video.', [
    { text: 'Keep filming', style: 'cancel' },
    { text: 'Stop', style: 'destructive', onPress: () => { setPhase('stopping'); recorder.current?.stopRecording().catch(() => {}); } },
  ]);

  const leave = () => { run.current.stop = true; stopVoice(); router.back(); };

  if (!camera.hasPermission || !device) {
    return (
      <View style={[styles.fill, styles.center]}>
        <Title color={c.ink}>{device ? 'Camera needed' : 'No camera found'}</Title>
        <Body color={c.ink2}>Allow the camera for Advantage AI in the iPhone Settings app to film a match.</Body>
        <Button title="Back" kind="nightLine" onPress={leave} />
      </View>
    );
  }

  const live = phase === 'recording' || phase === 'stopping';
  const late = elapsed >= WARN_RECORDING_MINUTES * 60_000;

  return (
    <View style={styles.fill}>
      <Camera
        style={StyleSheet.absoluteFill}
        isActive={phase !== 'stopped'}
        device={device}
        outputs={[video, photo]}
        constraints={[{ resolutionBias: video }, { fps: 30 }, { videoStabilizationMode: 'off' }]}
        orientationSource="interface"
        resizeMode="contain"
      />
      {live && !showPicture && <View style={[StyleSheet.absoluteFill, { backgroundColor: '#000000' }]} />}

      {phase === 'marking' && match ? (
        <View style={StyleSheet.absoluteFill}>
          <PageView path={markPath(match.job, info, auto)} onMessage={onPage} />
        </View>
      ) : (
        <View style={styles.panel}>
          {live && (
            <>
              <Text accessibilityLabel={`Recording, ${clock(elapsed)}`} style={styles.timer}>{clock(elapsed)}</Text>
              <Body color={c.ink2}>{late ? `Stops by itself at ${MAX_RECORDING_MINUTES}:00.` : 'Keep the app open; the screen stays on. Stop after the last point.'}</Body>
              <Button title="Stop" kind="danger" onPress={stop} busy={phase === 'stopping'} />
              <Pressable accessibilityRole="button" onPress={() => setShowPicture((v) => !v)} style={styles.link}>
                <Text style={{ color: c.ink2, fontSize: 15 }}>{showPicture ? 'Hide the camera picture (saves battery)' : 'Show the camera picture'}</Text>
              </Pressable>
            </>
          )}
          {phase === 'aim' && (
            <>
              <Title size={24} color={c.onNight}>Point at the whole court</Title>
              <Button title="Hands-free" kind="ball" onPress={handsFree} />
              <Button title="Mark the court myself" kind="nightLine" onPress={() => startMarking(false)} />
              <Pressable accessibilityRole="button" onPress={leave} style={styles.link}><Text style={{ color: c.ink2, fontSize: 15 }}>Not now</Text></Pressable>
            </>
          )}
          {(phase === 'handsfree' || phase === 'countdown') && (
            <>
              <Title size={22} color={c.onNight}>{tip}</Title>
              <Button title="Stop hands-free" kind="nightLine" onPress={() => { run.current.stop = true; stopVoice(); setPhase(match ? 'ready' : 'aim'); }} />
            </>
          )}
          {phase === 'ready' && (
            <>
              <Title size={24} color={c.onNight}>Ready to record</Title>
              <Body color={c.ink2}>Don&apos;t move the phone now.</Body>
              <Button title="Start recording" kind="ball" onPress={record} />
              <Pressable accessibilityRole="button" onPress={leave} style={styles.link}><Text style={{ color: c.ink2, fontSize: 15 }}>Not now</Text></Pressable>
            </>
          )}
          {phase === 'stopped' && <Title size={24} color={c.onNight}>Sending your match…</Title>}
          {!!problem && <Body color={c.lost}>{problem}</Body>}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#000000' },
  center: { justifyContent: 'center', padding: 24, gap: 12 },
  panel: { position: 'absolute', right: 24, top: 16, bottom: 16, width: 300, justifyContent: 'center', gap: 10, backgroundColor: 'rgba(0,0,0,0.72)', borderRadius: 20, padding: 16 },
  timer: { fontFamily: 'BarlowCondensed_700Bold', fontSize: 64, color: '#F2F5F1', fontVariant: ['tabular-nums'] },
  link: { minHeight: 44, justifyContent: 'center', alignItems: 'center' },
});
