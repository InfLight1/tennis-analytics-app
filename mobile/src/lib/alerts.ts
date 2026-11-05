// "Your report is ready": asked for after the first recording, never at first launch.
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { apiPost, type Creds } from './api';

Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false }),
});

export async function askForAlerts(creds: Creds) {
  if (!Device.isDevice) return;
  const projectId = Constants.expoConfig?.extra?.eas?.projectId as string | undefined;
  if (!projectId) return;                         // set when the app is linked to its build account
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== 'granted') return;
  const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId });
  await apiPost('/api/me/push-token', { token }, creds);
}

// Tapping the alert opens the report.
export function useReportAlerts() {
  const router = useRouter();
  const last = Notifications.useLastNotificationResponse();
  useEffect(() => {
    const job = last?.notification.request.content.data?.job;
    if (typeof job !== 'string') return;
    router.push({ pathname: '/report', params: { job } });
    Notifications.clearLastNotificationResponseAsync().catch(() => {});
  }, [last, router]);
}
