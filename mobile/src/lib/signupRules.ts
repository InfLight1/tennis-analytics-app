// The server's account rules (Code/accounts.py), checked while typing so mistakes show before the button.

export function usernameProblem(u: string): string | null {
  const v = u.trim().toLowerCase();
  if (!v) return null;
  if (!/^[a-z0-9_.-]*$/.test(v)) return 'Only letters, numbers, dots, dashes or underscores.';
  if (v.length < 3) return 'At least 3 characters.';
  if (v.length > 24) return 'At most 24 characters.';
  return null;
}

export function passwordProblem(p: string): string | null {
  if (!p || p.length >= 8) return null;
  return `${8 - p.length} more character${p.length === 7 ? '' : 's'} needed (at least 8).`;
}

export function codeProblem(c: string): string | null {
  if (!c || c.length === 6) return null;
  return 'Team codes are 6 letters.';
}
