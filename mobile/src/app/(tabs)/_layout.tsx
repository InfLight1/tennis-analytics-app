import { Tabs } from 'expo-router';
import { BallIcon, HomeIcon, ListIcon, PersonIcon } from '@/components/icons';
import { useAuth } from '@/lib/auth';
import { useTheme } from '@/lib/theme';

export default function TabsLayout() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const coach = user?.role === 'coach';
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarActiveTintColor: colors.ink,
      tabBarInactiveTintColor: colors.ink2,
      tabBarStyle: { backgroundColor: colors.tile, borderTopColor: colors.line },
      tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
      sceneStyle: { backgroundColor: colors.page },
    }}>
      <Tabs.Screen name="index" options={{ title: coach ? 'Team' : 'Dashboard', tabBarIcon: ({ color }) => <HomeIcon color={color} /> }} />
      <Tabs.Screen name="matches" options={{ title: 'Matches', href: coach ? null : undefined, tabBarIcon: ({ color }) => <ListIcon color={color} /> }} />
      <Tabs.Screen name="record" options={{ title: 'Record', tabBarIcon: () => <BallIcon /> }} />
      <Tabs.Screen name="account" options={{ title: 'Account', tabBarIcon: ({ color }) => <PersonIcon color={color} /> }} />
    </Tabs>
  );
}
