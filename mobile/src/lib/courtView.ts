// The drawn court seen from the back fence, where the phone films (same court as the landing page).
// Court metres: x across, y along (near end negative), z up. Pure maths so the intro and the sign-in band share it.

export const HW = 5.485, SW = 4.115, HL = 11.885, SL = 6.4;

export const LINES: [number, number, number, number][] = [
  [-HW, -HL, HW, -HL], [-HW, HL, HW, HL], [-HW, -HL, -HW, HL], [HW, -HL, HW, HL], [-SW, -HL, -SW, HL], [SW, -HL, SW, HL],
  [-SW, -SL, SW, -SL], [-SW, SL, SW, SL], [0, -SL, 0, SL], [0, -HL, 0, -HL + 0.3], [0, HL, 0, HL - 0.3],
];

export type Cam = { cx: number; cy: number; F: number; C: [number, number, number]; f: [number, number, number]; u: [number, number, number] };

// A camera high behind the near baseline, looking down the court. The far baseline lands at `top` and the
// near one at `bottom` (fractions of the height); the near corners may run off the sides, like a real phone shot.
export function makeCam(W: number, H: number, top = 0.3, bottom = 0.78): Cam {
  const C: [number, number, number] = [0, -HL - 6, 8.5];
  const T = [0, 2.5, 0];
  const d = [T[0] - C[0], T[1] - C[1], T[2] - C[2]];
  const n = Math.hypot(d[0], d[1], d[2]);
  const f: [number, number, number] = [d[0] / n, d[1] / n, d[2] / n];
  const u: [number, number, number] = [0, -f[2], f[1]];
  const unit: Cam = { cx: 0, cy: 0, F: 1, C, f, u };
  const tall = project(unit, 0, -HL)[1] - project(unit, 0, HL)[1];   // court height per unit of zoom
  const F = ((bottom - top) * H) / tall;
  const cam: Cam = { cx: W / 2, cy: 0, F, C, f, u };
  cam.cy = H * top - project(cam, 0, HL)[1];
  return cam;
}

// Screen x, y and scale (pixels per metre at that spot).
export function project(cam: Cam, x: number, y: number, z = 0): [number, number, number] {
  const dx = x - cam.C[0], dy = y - cam.C[1], dz = z - cam.C[2];
  const zc = Math.max(dx * 0 + dy * cam.f[1] + dz * cam.f[2], 0.5);
  const yc = dy * cam.u[1] + dz * cam.u[2];
  return [cam.cx + (cam.F * dx) / zc, cam.cy - (cam.F * yc) / zc, cam.F / zc];
}

export function polyPath(cam: Cam, pts: [number, number, number?][]): string {
  return pts.map(([x, y, z], i) => {
    const [a, b] = project(cam, x, y, z ?? 0);
    return `${i ? 'L' : 'M'}${a.toFixed(1)} ${b.toFixed(1)}`;
  }).join(' ') + ' Z';
}

export function linePath(cam: Cam, [x1, y1, x2, y2]: [number, number, number, number]): { d: string; len: number } {
  const a = project(cam, x1, y1), b = project(cam, x2, y2);
  return { d: `M${a[0].toFixed(1)} ${a[1].toFixed(1)} L${b[0].toFixed(1)} ${b[1].toFixed(1)}`, len: Math.hypot(b[0] - a[0], b[1] - a[1]) };
}
