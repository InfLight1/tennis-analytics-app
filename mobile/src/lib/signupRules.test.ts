import { codeProblem, passwordProblem, usernameProblem } from './signupRules';

describe('sign-up rules match the server', () => {
  it('accepts what the server accepts', () => {
    expect(usernameProblem('jordan_k')).toBeNull();
    expect(usernameProblem('Sam.Lee-2')).toBeNull();
    expect(usernameProblem('')).toBeNull();
  });
  it('flags bad usernames while typing', () => {
    expect(usernameProblem('jo')).toMatch(/3/);
    expect(usernameProblem('jo rdan')).toMatch(/Only/);
    expect(usernameProblem('a'.repeat(25))).toMatch(/24/);
  });
  it('counts how many password characters are missing', () => {
    expect(passwordProblem('1234567')).toBe('1 more character needed (at least 8).');
    expect(passwordProblem('12345678')).toBeNull();
    expect(passwordProblem('')).toBeNull();
  });
  it('wants 6-letter team codes', () => {
    expect(codeProblem('TIG')).not.toBeNull();
    expect(codeProblem('TIGERS')).toBeNull();
  });
});
