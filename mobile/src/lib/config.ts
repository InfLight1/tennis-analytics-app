// The server the app talks to. Stays on the test site until the live app can change after judging.
export const API_BASE = 'https://rudragoel10--tennis-perf-app-test-web-app.modal.run';

// The website's limits, kept the same in the app.
export const MAX_RECORDING_MINUTES = 60;
export const WARN_RECORDING_MINUTES = 55;

// Video is sent in pieces of this size, each its own background transfer.
export const PART_BYTES = 32 * 1024 * 1024;

// About 16 Mbit/s of video: a 50-minute match comes to about 6 GB.
export const VIDEO_BIT_RATE = 16_000_000;
export const BYTES_PER_MINUTE = (VIDEO_BIT_RATE / 8) * 60;
