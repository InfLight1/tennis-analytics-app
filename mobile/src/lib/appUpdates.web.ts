// The web preview has no over-the-air updates.
export function useAppUpdates(_canRestartNow: () => boolean) {}

export function useVersionLine(): string {
  return 'Version web preview';
}
