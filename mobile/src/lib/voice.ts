// The hands-free voice: the same recorded lines as the website, shipped inside the app so they
// work on a weak signal at the court.
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from 'expo-audio';

const CLIPS: Record<string, number> = {
  'Turn the phone sideways.': require('../../assets/voice/voice-tip-portrait.mp3'),
  "I can't see the court yet. Point the phone at the whole court from behind the baseline.": require('../../assets/voice/voice-tip-no-court.mp3'),
  'The far end is cut off. Tilt the phone up a little.': require('../../assets/voice/voice-tip-tilt-up.mp3'),
  'The near baseline is cut off. Tilt the phone down a little.': require('../../assets/voice/voice-tip-tilt-down.mp3'),
  'Both ends are cut off. Move the phone higher or further back.': require('../../assets/voice/voice-tip-too-close.mp3'),
  'The court is cut off on the left. Turn the phone a little to the left.': require('../../assets/voice/voice-tip-turn-left.mp3'),
  'The court is cut off on the right. Turn the phone a little to the right.': require('../../assets/voice/voice-tip-turn-right.mp3'),
  'The court looks small. Put the phone on the back fence, centred behind the baseline.': require('../../assets/voice/voice-tip-too-small.mp3'),
  'The phone is tilted sideways. Level it.': require('../../assets/voice/voice-tip-level.mp3'),
  'Almost. Hold still for a moment.': require('../../assets/voice/voice-tip-unsure.mp3'),
  'Good spot. Hold still.': require('../../assets/voice/voice-tip-good.mp3'),
  "Put the phone up on the fence, sideways, pointing at the court. I'll tell you how to aim it.": require('../../assets/voice/voice-intro.mp3'),
  "I can't reach the server. Check the signal.": require('../../assets/voice/voice-no-server.mp3'),
  "I see four players, so this is doubles. I'll check the alleys are in view too.": require('../../assets/voice/voice-doubles-seen.mp3'),
  'Good spot. Marking the singles court.': require('../../assets/voice/voice-marking-singles.mp3'),
  'Good spot. Marking the doubles court.': require('../../assets/voice/voice-marking-doubles.mp3'),
  'Something went wrong. Please take the phone down and check the screen.': require('../../assets/voice/voice-went-wrong.mp3'),
  'Please take the phone down and check the court lines on the screen.': require('../../assets/voice/voice-check-lines.mp3'),
  'Recording starts in 10 seconds.': require('../../assets/voice/voice-count-10.mp3'),
  '5': require('../../assets/voice/voice-count-5.mp3'),
  '3': require('../../assets/voice/voice-count-3.mp3'),
  '2': require('../../assets/voice/voice-count-2.mp3'),
  '1': require('../../assets/voice/voice-count-1.mp3'),
  'Recording. Good luck!': require('../../assets/voice/voice-recording.mp3'),
};

let player: AudioPlayer | null = null;

export async function prepareVoice() {
  // Plays with the silent switch on, and alongside the camera's microphone.
  await setAudioModeAsync({ playsInSilentMode: true, interruptionMode: 'mixWithOthers' }).catch(() => {});
}

export function say(line: string) {
  const clip = CLIPS[line];
  if (clip === undefined) return;
  player?.remove();
  player = createAudioPlayer(clip);
  player.play();
}

export function stopVoice() {
  player?.remove();
  player = null;
}
