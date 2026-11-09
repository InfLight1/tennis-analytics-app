// New screens and fixes arrive over the internet, no reinstall. The app looks for one at every open.
// If it downloads while the opening animation still shows, the app restarts into it straight away;
// otherwise it is used the next time the app opens. Changes to the phone parts still need a new build.
import * as Updates from 'expo-updates';
import { useEffect } from 'react';
import { Platform } from 'react-native';

export function useAppUpdates(canRestartNow: () => boolean) {
  useEffect(() => {
    if (Platform.OS === 'web' || __DEV__ || !Updates.isEnabled) return;
    (async () => {
      const check = await Updates.checkForUpdateAsync();
      if (!check.isAvailable) return;
      const got = await Updates.fetchUpdateAsync();
      if (got.isNew && canRestartNow()) await Updates.reloadAsync();
    })().catch(() => {});   // no signal: try again next open
  }, [canRestartNow]);
}
