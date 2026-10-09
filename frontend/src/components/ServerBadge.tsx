"use client";
import { useEffect, useState } from "react";
import { health } from "@/lib/api";

export default function ServerBadge() {
  const [state, setState] = useState<"checking" | "online" | "offline">("checking");
  const [model, setModel] = useState<string>("");

  useEffect(() => {
    let alive = true;
    const check = async () => {
      const h = await health();
      if (!alive) return;
      setState(h ? "online" : "offline");
      setModel(h ? String(h.model ?? "") : "");
    };
    check();
    const id = setInterval(check, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const style =
    state === "online" ? "bg-ok-soft text-ok" : state === "offline" ? "bg-warn-soft text-warn" : "bg-canvas text-muted";
  const text = state === "online" ? "API online" : state === "offline" ? "API asleep / offline" : "Checking API…";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs ${style}`} title={model} role="status">
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {text}
    </span>
  );
}
