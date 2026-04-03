import { useContext } from "react";
import { AuthContext } from "@/App";
import { toast } from "sonner";

export function useDemo() {
  const { user } = useContext(AuthContext);
  const isDemo = user?.is_demo || false;
  const isDemoViewer = isDemo && user?.roles?.[0]?.role !== "admin";

  const guardDemo = (action) => {
    if (isDemoViewer) {
      toast.error("Demo viewer: modifications are disabled. Register a free account to try all features.", { duration: 4000 });
      return true;
    }
    return false;
  };

  return { isDemo, isDemoViewer, guardDemo };
}
