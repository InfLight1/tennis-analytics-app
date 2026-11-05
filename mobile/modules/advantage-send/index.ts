// Background sending, built into the app for iPhone (see ios/SendManager.swift).
import { requireNativeModule, type EventSubscription } from 'expo-modules-core';

export type SendPhase = 'preparing' | 'sending' | 'finishing' | 'sign-in' | 'sent' | 'failed';
export type Send = { jobId: string; title: string; phase: SendPhase; sentBytes: number; totalBytes: number; problem?: string | null };
export type SendOptions = {
  jobId: string; title: string; filePath: string; apiBase: string;
  session: string | null; passcode: string | null; partBytes: number; r2: boolean;
};

type Native = {
  start(options: SendOptions): Promise<void>;
  list(): Promise<Send[]>;
  remove(jobId: string): Promise<void>;
  updateSignIn(session: string | null, passcode: string | null): Promise<void>;
  addListener(event: 'onChange', listener: () => void): EventSubscription;
};

const native = requireNativeModule<Native>('AdvantageSend');

export const startSend = (o: SendOptions) => native.start(o);
export const listSends = () => native.list();
export const removeSend = (jobId: string) => native.remove(jobId);
export const updateSendSignIn = (session: string | null, passcode: string | null) => native.updateSignIn(session, passcode);
export const onSendsChange = (listener: () => void) => native.addListener('onChange', listener);
