import { useState } from "react";
import { Button, Field, Modal, inputCls } from "./ui";

export default function SaveDialog({ initialName, initialDescription, isUpdate, onSave, onClose }: {
  initialName: string; initialDescription: string; isUpdate: boolean;
  onSave: (name: string, description: string) => Promise<void>; onClose: () => void;
}) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!name.trim()) { setError("Give your strategy a name."); return; }
    setBusy(true); setError(null);
    try { await onSave(name.trim(), description.trim()); }
    catch (e) { setError((e as Error).message); setBusy(false); }
  };

  return (
    <Modal title={isUpdate ? "Update saved strategy" : "Save strategy"} onClose={onClose}>
      <div className="p-5 space-y-4">
        <Field label="Name"><input autoFocus className={inputCls} value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} /></Field>
        <Field label="Description (optional)"><textarea className={inputCls} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        {error && <p role="alert" className="text-xs text-danger">{error}</p>}
      </div>
      <div className="px-5 py-4 border-t border-white/8 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={busy} onClick={submit}>{busy ? "Saving…" : isUpdate ? "Update" : "Save"}</Button>
      </div>
    </Modal>
  );
}
