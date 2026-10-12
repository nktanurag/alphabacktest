import { useEffect, useRef, useState } from "react";

interface GoogleId {
  initialize(o: { client_id: string; callback: (r: { credential: string }) => void }): void;
  renderButton(el: HTMLElement, o: Record<string, unknown>): void;
}
declare global {
  interface Window { google?: { accounts: { id: GoogleId } } }
}

let loading: Promise<void> | null = null;
function loadGoogleScript(): Promise<void> {
  if (window.google) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => { loading = null; reject(new Error("Could not load Google sign-in.")); };
    document.head.appendChild(s);
  });
  return loading;
}

/** Google's own sign-in button; calls `onCredential` with the ID token after sign-in. */
export default function GoogleButton({ clientId, onCredential }: {
  clientId: string; onCredential: (credential: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const callback = useRef(onCredential);
  callback.current = onCredential;
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadGoogleScript().then(() => {
      if (cancelled || !ref.current || !window.google) return;
      window.google.accounts.id.initialize({ client_id: clientId, callback: (r) => callback.current(r.credential) });
      window.google.accounts.id.renderButton(ref.current, { theme: "outline", size: "large", text: "signin_with", shape: "pill" });
    }).catch((e: Error) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [clientId]);

  return error
    ? <p role="alert" className="text-xs text-danger">{error}</p>
    : <div ref={ref} className="min-h-10" />;
}
