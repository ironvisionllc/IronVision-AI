import { useEffect, useRef, useContext, useCallback } from "react";
import { AuthContext } from "@/App";

const INACTIVITY_TIMEOUT = 5 * 60 * 1000; // 5 minutes

export function useInactivityLogout() {
  const { user, logout } = useContext(AuthContext);
  const timerRef = useRef(null);

  const resetTimer = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      if (user) {
        logout();
        // Small delay to ensure state updates before alert
        setTimeout(() => {
          window.location.href = "/login";
        }, 100);
      }
    }, INACTIVITY_TIMEOUT);
  }, [user, logout]);

  useEffect(() => {
    if (!user) return;

    const events = ["mousedown", "mousemove", "keydown", "scroll", "touchstart", "click"];
    
    const handler = () => resetTimer();
    events.forEach(e => window.addEventListener(e, handler, { passive: true }));
    resetTimer();

    return () => {
      events.forEach(e => window.removeEventListener(e, handler));
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [user, resetTimer]);
}
