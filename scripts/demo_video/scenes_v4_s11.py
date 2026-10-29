"""Re-records only scene 11 (audit log, IPs masked) as a 10 s clip for splicing into /tmp/v4_raw.mp4 at 162–172 s."""
import scenes_marketing as m
import scenes_v4 as v

T = {11: (0, 10)}


async def s11(A, p):
    await m.setup(A, p)
    v.T[11] = T[11]
    await v.s11(A, p)


SCENES = [s11]
