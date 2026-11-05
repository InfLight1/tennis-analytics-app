import * as SecureStore from 'expo-secure-store';

export const store = {
  get: (key: string) => SecureStore.getItemAsync(key).catch(() => null),
  set: (key: string, value: string | null) =>
    (value ? SecureStore.setItemAsync(key, value) : SecureStore.deleteItemAsync(key)).catch(() => {}),
};
