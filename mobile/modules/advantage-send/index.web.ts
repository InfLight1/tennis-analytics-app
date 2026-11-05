// Browser stand-in, only used to look at the screens on a computer.
import type { Send, SendOptions } from './index';

export type { Send, SendOptions, SendPhase } from './index';

export const startSend = async (_o: SendOptions) => {};
export const listSends = async (): Promise<Send[]> => [];
export const removeSend = async (_jobId: string) => {};
export const updateSendSignIn = async (_session: string | null, _passcode: string | null) => {};
export const onSendsChange = (_listener: () => void) => ({ remove() {} });
