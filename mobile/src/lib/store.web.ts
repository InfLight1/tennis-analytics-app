// Browser stand-in, only used to look at the screens on a computer.
export const store = {
  get: async (key: string) => localStorage.getItem(key),
  set: async (key: string, value: string | null) => {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  },
};
