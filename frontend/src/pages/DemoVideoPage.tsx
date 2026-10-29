import { Link } from "react-router-dom";
import { Download } from "lucide-react";
import { BrandLockup } from "@/components/shell/Brand";
import { SyntheticBanner } from "@/components/shell/SyntheticBanner";

const BASE = `${process.env.REACT_APP_BACKEND_URL}/api/v1/public/demo`;
const FILES: [string, string, string][] = [
  ["ironvision_ai_rmf_demo.mp4", "Demo video (MP4, 1920×1080, silent, 3:45)", "demo-dl-mp4"],
  ["ironvision_ai_rmf_narration.txt", "Narration script (ElevenLabs-ready, timed blocks)", "demo-dl-narration"],
  ["ironvision_ai_rmf_teleprompter.md", "Teleprompter script", "demo-dl-teleprompter"],
  ["ironvision_ai_rmf_captions.srt", "Captions (SRT)", "demo-dl-captions"],
  ["ironvision_ai_rmf_scene_timeline.md", "Scene timeline", "demo-dl-timeline"],
  ["ironvision_ai_rmf_demo_validation.md", "Validation report", "demo-dl-validation"],
];

export default function DemoVideoPage() {
  return (
    <div className="flex min-h-full flex-col" data-testid="demo-video-page">
      <SyntheticBanner />
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
        <BrandLockup className="w-36" />
        <p className="eyebrow mt-6">Product demo · October 2026 · synthetic data</p>
        <h1 className="t-headline mt-2 text-slate-900" data-testid="demo-video-title">IronVision AI – RMF product demo</h1>
        <p className="mt-2 text-[15px] text-slate-600">A 3¾-minute silent tour of how IronVision makes RMF simpler, faster and more connected – from CNSSI 1253 categorization to the AO's decision. AI makes suggestions;
          people make every assessment, approval and authorization decision. Narration is coming; the timed narration script and captions are available below.</p>
        <video className="mt-6 w-full rounded-lg border border-slate-200 bg-black" controls playsInline preload="metadata"
          src={`${BASE}/ironvision_ai_rmf_demo.mp4`} data-testid="demo-video-player" />
        <ul className="mt-6 grid gap-2 sm:grid-cols-2" data-testid="demo-downloads">
          {FILES.map(([f, label, id]) => (
            <li key={f}><a className="btn-outline w-full justify-start px-3 py-2 text-left" href={`${BASE}/${f}`} data-testid={id}>
              <Download className="h-4 w-4 shrink-0" aria-hidden /> <span className="truncate">{label}</span></a></li>))}
        </ul>
        <p className="mt-6 text-[14px] text-slate-700">Want more detail?{" "}
          <a className="text-blue-800 underline" href={`${BASE}/ironvision_ai_rmf_technical_walkthrough.mp4`} data-testid="demo-technical-walkthrough-link">Technical walkthrough (5 min)</a></p>
        <div className="mt-8 flex gap-5 text-[13px]">
          <Link to="/whitepaper" className="text-blue-800 underline" data-testid="demo-video-whitepaper-link">Whitepaper</Link>
          <Link to="/login" className="text-blue-800 underline" data-testid="demo-video-back-login">Back to sign in</Link>
        </div>
      </main>
    </div>
  );
}
