import { useEffect, useState } from "react";

type Row = Record<string, any>;

interface Props {
  ai: Row;
  onSave: (model: string) => void;
}

export function AiModelSettings({ ai, onSave }: Props) {
  const eff: Row = ai.effective ?? {};
  const [model, setModel] = useState<string>(ai.model ?? "");
  useEffect(() => setModel(ai.model ?? ""), [ai.model]);
  const examples: string[] = ai.model_examples ?? [];
  const perUseCase = Object.entries((eff.models ?? {}) as Row).filter(([k, v]) => k !== "default" && v);

  return (
    <div className="space-y-2" data-testid="ai-model-settings">
      <div className="grid gap-1 rounded border border-slate-200 bg-slate-50 p-2 font-mono text-[12px] text-slate-700 sm:grid-cols-3">
        <div>provider <b data-testid="ai-effective-provider">{eff.provider ?? ai.provider}</b></div>
        <div className="truncate">base URL <b data-testid="ai-effective-base-url">{eff.base_url ?? "—"}</b></div>
        <div>model <b data-testid="ai-effective-model">{ai.model ?? "—"}</b> <span className="text-slate-500">({ai.model_source})</span></div>
        <div data-testid="ai-effective-key">API key {eff.api_key_configured ? "configured (hidden)" : eff.provider === "anthropic" ? "env-managed" : "not set"}</div>
        <div className="sm:col-span-2" data-testid="ai-effective-status">{eff.configured ? "configured" : `not configured – ${eff.reason ?? ""}`}</div>
        {perUseCase.length > 0 && <div className="sm:col-span-3" data-testid="ai-usecase-models">per use case: {perUseCase.map(([k, v]) => `${k}=${v}`).join(" · ")}</div>}
      </div>
      <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); onSave(model.trim()); }}>
        <label className="flex min-w-[18rem] flex-1 flex-col text-[12px] text-slate-600">
          Model (any provider slug – leave empty to use AI_MODEL)
          <input className="input mt-1 font-mono" list="ai-model-examples" value={model} onChange={(e) => setModel(e.target.value)}
                 placeholder="e.g. openai/gpt-4o" maxLength={200} data-testid="ai-model-input" />
          <datalist id="ai-model-examples">{examples.map((m) => <option key={m} value={m} />)}</datalist>
        </label>
        <button type="submit" className="btn-primary" data-testid="ai-model-save-btn">Save model</button>
      </form>
      <div className="text-[11px] text-slate-500">Examples: {examples.join(", ")}. The admin model overrides AI_MODEL and the per-use-case AI_MODEL_* values; run the smoke test after changing it.</div>
    </div>
  );
}
