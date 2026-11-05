import { Stack } from 'expo-router';
import { PageView } from '@/components/PageView';

// The example report, for people who haven't signed in yet.
export default function Example() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Example report' }} />
      <PageView path="/example" />
    </>
  );
}
