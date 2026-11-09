// New screens and fixes arrive over the internet, no reinstall. The phone looks for one at every open
// (expo-updates' own check, app.json "ON_LOAD") and downloads it in the background. If it is ready while
// the opening animation still shows, the app restarts into it; otherwise it is used at the next open.
// Changes to the phone parts (camera, permissions, new libraries) still need a new build.
import * as Updates from 'expo-updates';
import { useEffect } from 'react';

export function useAppUpdates(canRestartNow: () => boolean) {
  const { isUpdatePending } = Updates.useUpdates();
  useEffect(() => {
    if (isUpdatePending && canRestartNow()) Updates.reloadAsync().catch(() => {});
  }, [isUpdatePending, canRestartNow]);
}

// One small line for the Account and sign-in screens, so we can tell which version a phone runs.
export function useVersionLine(): string {
  const { currentlyRunning, isUpdatePending, isDownloading, checkError, downloadError } = Updates.useUpdates();
  const running = currentlyRunning.isEmbeddedLaunch || !currentlyRunning.updateId
    ? 'built-in'
    : `update ${currentlyRunning.updateId.slice(0, 8)}`;
  const state = isUpdatePending ? ' · new version ready, reopen the app'
    : isDownloading ? ' · downloading a new version'
    : '';
  const problem = checkError ?? downloadError;
  return `Test update 1 arrived · Version ${running}${state}${problem ? ` · update problem: ${problem.message}` : ''}`;
}
