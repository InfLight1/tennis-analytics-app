// Save as PDF: pages can't print themselves from inside an app, so the page hands over its
// print layout and the phone makes the file for the share sheet.
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

export async function savePdf(html: string) {
  const { uri } = await Print.printToFileAsync({ html });
  await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle: 'Save your report' });
}
