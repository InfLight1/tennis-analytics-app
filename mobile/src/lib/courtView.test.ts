import { HL, HW, makeCam, project } from './courtView';

describe('court seen from the back fence', () => {
  const cam = makeCam(390, 844, 0.3);

  it('puts the far baseline where asked and the near one lower', () => {
    expect(project(cam, 0, HL)[1]).toBeCloseTo(844 * 0.3, 3);
    expect(project(cam, 0, -HL)[1]).toBeGreaterThan(project(cam, 0, HL)[1]);
  });

  it('draws the far end narrower than the near end, centred', () => {
    const near = project(cam, HW, -HL)[0] - project(cam, -HW, -HL)[0];
    const far = project(cam, HW, HL)[0] - project(cam, -HW, HL)[0];
    expect(far).toBeLessThan(near);
    expect(project(cam, 0, 0)[0]).toBeCloseTo(195, 3);
  });

  it('puts the near baseline where asked', () => {
    expect(project(cam, 0, -HL)[1]).toBeCloseTo(844 * 0.78, 3);
  });
});
