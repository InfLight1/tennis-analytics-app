import { BYTES_PER_MINUTE } from './config';
import { markPath, matchTitle, roomMinutes, spaceWarning } from './match';

const info = { type: 'doubles' as const, near: 'Alex & Jo', far: '' };

describe('markPath', () => {
  it('passes the match details to the marking page', () => {
    const q = new URLSearchParams(markPath('abc', info, true).split('?')[1]);
    expect(q.get('mark')).toBe('abc');
    expect(q.get('type')).toBe('doubles');
    expect(q.get('p1')).toBe('Alex & Jo');
    expect(q.get('auto')).toBe('1');
  });
  it('leaves auto off for a hand-marked court', () => {
    expect(markPath('abc', info, false)).not.toContain('auto');
  });
});

describe('matchTitle', () => {
  it('fills in a missing name', () => {
    expect(matchTitle(info)).toBe('Alex & Jo vs Player 2');
  });
});

describe('spaceWarning', () => {
  it('is quiet when a full match fits', () => {
    expect(spaceWarning(BYTES_PER_MINUTE * 61)).toBeNull();
  });
  it('warns when a long match may not fit', () => {
    expect(spaceWarning(BYTES_PER_MINUTE * 30)).toMatchObject({ block: false });
  });
  it('stops a recording that would barely start', () => {
    expect(spaceWarning(BYTES_PER_MINUTE * 5)).toMatchObject({ block: true });
  });
  it('counts whole minutes', () => {
    expect(roomMinutes(BYTES_PER_MINUTE * 2.5)).toBe(2);
  });
});
