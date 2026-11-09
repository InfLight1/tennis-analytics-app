// The Court look (DESIGN.md) for the app's native parts, in light and dark.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Appearance, useColorScheme } from 'react-native';
import { store } from './store';

export const palettes = {
  light: {
    page: '#EDF0F2', tile: '#FFFFFF', tile2: '#F4F6F7', line: '#DCE1E4', line2: '#C3CBCF',
    ink: '#0F1A14', ink2: '#47534D', ink3: '#5F6A64',
    ball: '#C6DA2C', ballInk: '#0F1A14', ballSoft: '#EFF5C8',
    lost: '#C2412F', lostSoft: '#FBE5E1',
    night: '#0F1A14', night2: '#1D2A22', onNight: '#F2F5F1', onNight2: '#B9C4BD',
  },
  dark: {
    page: '#0E1113', tile: '#1A1E21', tile2: '#23282C', line: '#2E3438', line2: '#41494E',
    ink: '#EEF2EF', ink2: '#B3BDB8', ink3: '#8F9A95',
    ball: '#C6DA2C', ballInk: '#0F1A14', ballSoft: '#2A3214',
    lost: '#F2836F', lostSoft: '#3A221E',
    night: '#000000', night2: '#1D2A22', onNight: '#F2F5F1', onNight2: '#B9C4BD',
  },
};
export type Colors = typeof palettes.light;

// The drawn night court (tokens.css --court-*), the same in light and dark: it is the brand scene.
export const court = { deep: '#0A1410', out: '#154734', inn: '#1E7A52', line: '#EEF2EF' };

// Fonts, option C (Rudra, Nov 4): Newsreader big titles, Apple's font for the rest, scoreboard numbers.
export const fonts = {
  title: 'Newsreader_500Medium',
  board: 'BarlowCondensed_700Bold',
};
export const radius = { tile: 20, box: 12, pill: 999 };

export type Appearance_ = 'auto' | 'light' | 'dark';
export type Scheme = 'light' | 'dark';
const KEY = 'appearance';

export function schemeFor(choice: Appearance_, phone: Scheme): Scheme {
  return choice === 'auto' ? phone : choice;
}

type Theme = { colors: Colors; scheme: Scheme; choice: Appearance_; setChoice: (c: Appearance_) => void };
const ThemeContext = createContext<Theme | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const phone: Scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const [choice, setChoiceState] = useState<Appearance_>('auto');

  useEffect(() => {
    store.get(KEY).then((saved) => {
      if (saved === 'light' || saved === 'dark') {
        setChoiceState(saved);
        Appearance.setColorScheme(saved);
      }
    });
  }, []);

  const setChoice = useCallback((c: Appearance_) => {
    setChoiceState(c);
    Appearance.setColorScheme(c === 'auto' ? 'unspecified' : c);
    store.set(KEY, c);
  }, []);

  const value = useMemo(() => {
    const scheme = schemeFor(choice, phone);
    return { colors: palettes[scheme], scheme, choice, setChoice };
  }, [choice, phone, setChoice]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  const t = useContext(ThemeContext);
  if (!t) throw new Error('useTheme needs ThemeProvider');
  return t;
}
