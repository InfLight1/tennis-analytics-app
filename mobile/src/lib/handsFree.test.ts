import { aimStep, clock, LINES, REPEAT_MS, startAim } from './handsFree';

const good = { tip: 'Good spot. Hold still.', code: 'good', ok: true, on_court: 2 };
const left = { tip: 'Turn left.', code: 'left', ok: false, on_court: 2 };

describe('aimStep', () => {
  it('needs two good answers in a row before marking', () => {
    const first = aimStep(startAim(false), good, 1000);
    expect(first.step.next).toBe('wait');
    expect(aimStep(first.state, good, 2000).step).toEqual({ next: 'mark' });
  });
  it('starts over when the phone moves off', () => {
    const first = aimStep(startAim(false), good, 1000);
    const moved = aimStep(first.state, left, 2000);
    expect(moved.state.goods).toBe(0);
    expect(aimStep(moved.state, good, 3000).step.next).toBe('wait');
  });
  it("says a tip once, then repeats it after a while", () => {
    const first = aimStep(startAim(false), left, 20000);
    expect(first.step).toMatchObject({ say: 'Turn left.' });
    const same = aimStep(first.state, left, 21000);
    expect(same.step).toMatchObject({ say: undefined });
    expect(aimStep(same.state, left, 20000 + REPEAT_MS + 1).step).toMatchObject({ say: 'Turn left.' });
  });
  it('switches to doubles after seeing 3+ players twice', () => {
    const crowded = { ...left, on_court: 4 };
    const first = aimStep(startAim(false), crowded, 1000);
    const second = aimStep(first.state, crowded, 2000);
    expect(second.step).toMatchObject({ next: 'doubles', say: LINES.doubles });
    expect(second.state.doubles).toBe(true);
  });
  it('never switches back from doubles', () => {
    const r = aimStep(startAim(true), { ...left, on_court: 1 }, 1000);
    expect(r.state.doubles).toBe(true);
  });
  it('asks for signal when the server does not answer', () => {
    const r = aimStep(startAim(false), null, 20000);
    expect(r.step).toMatchObject({ say: LINES.noServer, waitMs: 3000 });
    expect(aimStep(r.state, null, 21000).step).toMatchObject({ say: undefined });
  });
});

describe('clock', () => {
  it('shows minutes, then hours', () => {
    expect(clock(65_000)).toBe('1:05');
    expect(clock(3_725_000)).toBe('1:02:05');
  });
});
