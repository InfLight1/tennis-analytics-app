import { useLocalSearchParams } from 'expo-router';
import { PageView } from '@/components/PageView';

// Pages that are only ever a link away: how to film, privacy, the example report.
export default function Page() {
  const { path } = useLocalSearchParams<{ path: string }>();
  return <PageView path={path} />;
}
