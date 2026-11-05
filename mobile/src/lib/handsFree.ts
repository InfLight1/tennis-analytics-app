// Hands-free aiming, same rules as the website (web_assets/record_match.js): a tip is said out
// loud until two "good" answers in a row, and 3+ players on court twice in a row means doubles.
export type AimAnswer = { tip?: string; code?: string; ok?: boolean; on_court?: number | null };

export type AimState = { goods: number; crowd: number; lastCode: string; lastSpoke: number; doubles: boolean };
export const startAim = (doubles: boolean): AimState => ({ goods: 0, crowd: 0, lastCode: '', lastSpoke: 0, doubles });

export const REPEAT_MS = 9000;
const DOUBLES_SEEN = 2;
const GOODS_NEEDED = 2;

export type AimStep =
  | { say?: string; next: 'wait'; waitMs: number }
  | { say: string; next: 'doubles'; waitMs: number }
  | { next: 'mark' };

export const LINES = {
  intro: "Put the phone up on the fence, sideways, pointing at the court. I'll tell you how to aim it.",
  noServer: "I can't reach the server. Check the signal.",
  doubles: "I see four players, so this is doubles. I'll check the alleys are in view too.",
  marking: (doubles: boolean) => `Good spot. Marking the ${doubles ? 'doubles' : 'singles'} court.`,
  wrong: 'Something went wrong. Please take the phone down and check the screen.',
  check: 'Please take the phone down and check the court lines on the screen.',
  recording: 'Recording. Good luck!',
};

export const COUNTDOWN: [string, number][] = [
  ['Recording starts in 10 seconds.', 5000], ['5', 2000], ['3', 1000], ['2', 1000], ['1', 1000],
];

export function aimStep(state: AimState, answer: AimAnswer | null, now: number): { state: AimState; step: AimStep } {
  if (!answer || !answer.tip) {
    const speak = now - state.lastSpoke > REPEAT_MS;
    return {
      state: speak ? { ...state, lastSpoke: now } : state,
      step: { say: speak ? LINES.noServer : undefined, next: 'wait', waitMs: 3000 },
    };
  }
  let crowd = state.crowd;
  if (!state.doubles && answer.on_court != null) crowd = answer.on_court >= 3 ? crowd + 1 : 0;
  if (!state.doubles && crowd >= DOUBLES_SEEN) {
    return {
      state: { ...state, crowd, doubles: true, goods: 0, lastCode: 'doubles', lastSpoke: now },
      step: { say: LINES.doubles, next: 'doubles', waitMs: 3000 },
    };
  }
  const goods = answer.ok ? state.goods + 1 : 0;
  if (goods >= GOODS_NEEDED) return { state: { ...state, crowd, goods }, step: { next: 'mark' } };
  const speak = answer.code !== state.lastCode || now - state.lastSpoke > REPEAT_MS;
  return {
    state: { ...state, crowd, goods, lastCode: speak ? answer.code ?? '' : state.lastCode, lastSpoke: speak ? now : state.lastSpoke },
    step: { say: speak ? answer.tip : undefined, next: 'wait', waitMs: answer.ok ? 500 : 1500 },
  };
}

export function clock(ms: number): string {
  const t = Math.floor(ms / 1000);
  const h = Math.floor(t / 3600);
  const m = Math.floor(t / 60) % 60;
  const s = String(t % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}
