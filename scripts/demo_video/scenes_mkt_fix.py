"""Pick-up recording for the 3:10 cut: Policy Auditor (2:00 budget 35 s), Mapping Review (10 s) and Authorization (20 s), recorded
back-to-back from virtual 0 and spliced into the published video by splice_mkt.py. Run: DEMO_SCENES=scenes_mkt_fix DEMO_OUT=/tmp/demo_fix"""
import scenes_marketing as m

m.T.update({6: (0, 35), 7: (35, 45), 9: (45, 65)})


async def s6(A, p):
    await m.setup(A, p)
    await m.s6(A, p)


SCENES = [s6, m.s7, m.s9]
