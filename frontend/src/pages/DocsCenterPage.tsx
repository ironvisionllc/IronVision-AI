import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpen, Download, FileArchive, FileText } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { PageHeader } from "@/components/common/Panel";
import { cn, fmtDate } from "@/lib/format";

interface DocMeta { slug: string; title: string; path: string; available: boolean; bytes: number; updated_at: string | null }
interface Doc extends DocMeta { markdown: string }

async function download(url: string, filename: string) {
  const r = await api.get(url, { responseType: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(r.data);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

const fileName = (path: string) => path.split("/").pop() ?? "doc.md";

export default function DocsCenterPage() {
  const { slug = "digitalocean" } = useParams();
  const [items, setItems] = useState<DocMeta[]>([]);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => { api.get<{ items: DocMeta[] }>("/docs-center").then((r) => setItems(r.data.items)).catch((e) => setErr(errorMessage(e))); }, []);
  useEffect(() => {
    setDoc(null); setErr("");
    api.get<Doc>(`/docs-center/${slug}`).then((r) => setDoc(r.data)).catch((e) => setErr(errorMessage(e)));
  }, [slug]);

  return (
    <div data-testid="docs-center-page">
      <PageHeader title="Handover Docs" subtitle="Read-only repository documentation served from an allowlist. Rendered from the same Markdown files shipped in the repo.">
        <button className="btn-primary" onClick={() => download("/docs-center/archive.zip", "ironvision-ai-docs.zip")} data-testid="docs-download-all-btn">
          <FileArchive className="h-4 w-4" aria-hidden /> Download all docs (.zip)
        </button>
      </PageHeader>
      <div className="grid gap-5 lg:grid-cols-[17rem_1fr]">
        <nav className="panel h-max p-2 lg:sticky lg:top-0" aria-label="Documents" data-testid="docs-list">
          {items.map((d) => (
            <Link key={d.slug} to={`/docs-center/${d.slug}`} data-testid={`docs-link-${d.slug}`} aria-current={d.slug === slug ? "page" : undefined}
              className={cn("flex items-start gap-2 rounded-lg px-3 py-2 text-[13px] transition-colors duration-150",
                d.slug === slug ? "bg-blue-50 font-semibold text-blue-800" : "text-slate-700 hover:bg-slate-100", !d.available && "opacity-50")}>
              <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="min-w-0"><span className="block leading-snug">{d.title}</span><span className="block font-mono text-[10px] text-slate-500">{d.path}</span></span>
            </Link>
          ))}
        </nav>
        <article className="panel min-w-0 p-7" data-testid="docs-article">
          {err && <div role="alert" className="rounded-lg border border-rose-300 bg-rose-50 p-3 text-[13px] text-rose-800" data-testid="docs-error">{err}</div>}
          {!doc && !err && <div className="text-[13px] text-slate-500">Loading…</div>}
          {doc && <>
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b pb-4" style={{ borderColor: "var(--iv-border)" }}>
              <div className="flex items-center gap-2 text-[12px] text-slate-500">
                <BookOpen className="h-4 w-4 text-blue-700" aria-hidden />
                <span className="font-mono" data-testid="docs-path">{doc.path}</span>
                <span>· {(doc.bytes / 1024).toFixed(1)} KB · updated {doc.updated_at ? fmtDate(doc.updated_at) : "—"}</span>
              </div>
              <button className="btn-secondary px-2.5 py-1 text-xs" onClick={() => download(`/docs-center/${doc.slug}/download`, fileName(doc.path))} data-testid="docs-download-btn">
                <Download className="h-3.5 w-3.5" aria-hidden /> Download (.md)
              </button>
            </div>
            <div className="iv-prose" data-testid="docs-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{doc.markdown}</ReactMarkdown></div>
          </>}
        </article>
      </div>
    </div>
  );
}
