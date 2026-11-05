import { View } from 'react-native';
import { PageView } from '@/components/PageView';
import { SendingList } from '@/components/SendingList';
import { useAuth } from '@/lib/auth';

// Players get the dashboard; a coach's home is the team page, as on the website.
export default function Home() {
  const { user } = useAuth();
  return (
    <View style={{ flex: 1 }}>
      <PageView path={user?.role === 'coach' ? '/account' : '/app'} reloadOnFocus />
      <SendingList floating />
    </View>
  );
}
