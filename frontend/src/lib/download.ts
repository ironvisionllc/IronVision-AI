import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";

/** Download an authenticated file (Blob + anchor with a filename) and confirm with a toast. */
export async function downloadFile(path: string, filename: string, label: string) {
  try {
    const r = await api.get(path, { responseType: "blob" });
    const cd = String(r.headers?.["content-disposition"] || "");
    const name = /filename="?([^";]+)"?/.exec(cd)?.[1] || filename;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(r.data as Blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast.success(`${label} downloaded`, { description: `${name} – saved to your downloads folder.` });
  } catch (e) {
    toast.error(`Could not download ${label.toLowerCase()}`, { description: errorMessage(e) });
  }
}
