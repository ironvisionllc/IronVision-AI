import { Link } from "react-router-dom";
import { Download, FileText } from "lucide-react";
import { BrandLockup } from "@/components/shell/Brand";
import { SyntheticBanner } from "@/components/shell/SyntheticBanner";

const BASE = `${process.env.REACT_APP_BACKEND_URL}/api/v1/public`;
const CHAPTERS = ["Executive summary & problem statement", "Personas, RBAC & separation of duties", "All 7 RMF steps (NIST SP 800-37)",
  "Screen-by-screen guide", "AI components & guardrails", "CNSSI 1253, NIST 800-53 Rev 5 & CCI reference content", "Evidence integrity",
  "eMASS TR and HW/SW workbooks", "Architecture, security & deployment", "Limitations, roadmap, glossary & API summary"];

export default function WhitepaperPage() {
  return (
    <div className="flex min-h-full flex-col" data-testid="whitepaper-page">
      <SyntheticBanner />
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
        <BrandLockup className="w-40" />
        <p className="eyebrow mt-8">Whitepaper · Version 1.0 · October 2026</p>
        <h1 className="t-headline mt-2 text-slate-900" data-testid="whitepaper-title">IronVision AI – human-approved AI for the NIST RMF</h1>
        <p className="mt-3 text-[15px] text-slate-600">A detailed description of what the product does today, written from the code and its test reports.
          Simulated capabilities are labelled MOCKED. Items that need human verification or SME review are marked as such.</p>
        <div className="mt-7 flex flex-wrap gap-3">
          <a className="btn-primary px-4 py-2.5" href={`${BASE}/whitepaper.pdf`} data-testid="whitepaper-download-pdf"><Download className="h-4 w-4" aria-hidden /> Download PDF</a>
          <a className="btn-outline px-4 py-2.5" href={`${BASE}/whitepaper.docx`} data-testid="whitepaper-download-docx"><FileText className="h-4 w-4" aria-hidden /> Download Word (DOCX)</a>
        </div>
        <div className="panel mt-9 p-6">
          <h2 className="t-title text-slate-900">What's inside</h2>
          <ul className="mt-3 grid gap-x-6 gap-y-1.5 text-[14px] text-slate-700 sm:grid-cols-2" data-testid="whitepaper-chapters">
            {CHAPTERS.map((c) => <li key={c} className="flex gap-2"><span className="text-blue-700">•</span>{c}</li>)}
          </ul>
        </div>
        <Link to="/login" className="mt-8 inline-block text-[13px] text-blue-800 underline" data-testid="whitepaper-back-login">Back to sign in</Link>
      </main>
    </div>
  );
}
