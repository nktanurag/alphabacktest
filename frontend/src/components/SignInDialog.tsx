import { useState } from "react";
import { loginWithGoogle, type User } from "../api";
import GoogleButton from "./GoogleButton";
import { Button, Modal } from "./ui";

export default function SignInDialog({ clientId, reason, onSignedIn, onClose }: {
  clientId: string; reason: string; onSignedIn: (u: User) => void; onClose: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  const handle = (credential: string) => {
    setError(null);
    loginWithGoogle(credential).then(onSignedIn).catch((e: Error) => setError(e.message));
  };

  return (
    <Modal title="Sign in" onClose={onClose}>
      <div className="p-5 space-y-4">
        <p className="text-sm text-slate-400">{reason}</p>
        <GoogleButton clientId={clientId} onCredential={handle} />
        {error && <p role="alert" className="text-xs text-danger">{error}</p>}
      </div>
      <div className="px-5 py-4 border-t border-white/8 flex justify-end">
        <Button variant="ghost" onClick={onClose}>Not now</Button>
      </div>
    </Modal>
  );
}
