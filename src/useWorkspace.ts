import { useCallback, useEffect, useRef, useState } from "react";
import type { Api, Workspace } from "./erp-types";

export function useWorkspace() {
  const [data, setData] = useState<Workspace | null>(null);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const admin = useRef("");
  const bootstrap = useCallback(async () => {
    const response = await fetch("/api/studio/bootstrap");
    if (!response.ok)
      throw new Error("Cannot connect to the operations server.");
    admin.current = (await response.json()).admin_key;
    return admin.current;
  }, []);
  const api: Api = useCallback(
    async <T>(path: string, method = "GET", body?: unknown): Promise<T> => {
      if (!admin.current) await bootstrap();
      const send = () =>
        fetch("/api/studio" + path, {
          method,
          headers: {
            "Content-Type": "application/json",
            "X-Demo-Admin": admin.current,
          },
          ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        });
      let response = await send();
      if (response.status === 403) {
        await bootstrap();
        response = await send();
      }
      const payload = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : Array.isArray(payload.detail)
              ? payload.detail.map((e: { msg: string }) => e.msg).join("; ")
              : "The request could not be completed.",
        );
      return payload as T;
    },
    [bootstrap],
  );
  const reload = useCallback(async () => {
    try {
      const next = await api<Workspace>("/state");
      setData(next);
      setLoading(false);
      return next;
    } catch (e) {
      setError((e as Error).message);
      setLoading(false);
      throw e;
    }
  }, [api]);
  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout>;
    let refresh: ReturnType<typeof setTimeout>;
    async function connect() {
      try {
        const key = await bootstrap();
        if (stopped) return;
        await reload();
        if (stopped) return;
        socket = new WebSocket(
          `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/studio/ws`,
        );
        socket.onopen = () => socket?.send(JSON.stringify({ key }));
        socket.onmessage = (event) => {
          const message = JSON.parse(event.data);
          if (message.type === "ready") setConnected(true);
          else {
            clearTimeout(refresh);
            refresh = setTimeout(() => reload().catch(() => {}), 100);
          }
        };
        socket.onclose = () => {
          setConnected(false);
          if (!stopped) retry = setTimeout(connect, 1500);
        };
        socket.onerror = () => setConnected(false);
      } catch (e) {
        if (!stopped) {
          setError((e as Error).message);
          retry = setTimeout(connect, 2000);
        }
      }
    }
    connect();
    const ping = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
    }, 25000);
    const onFocus = () => reload().catch(() => {});
    window.addEventListener("focus", onFocus);
    return () => {
      stopped = true;
      clearTimeout(retry);
      clearTimeout(refresh);
      clearInterval(ping);
      window.removeEventListener("focus", onFocus);
      socket?.close();
    };
  }, [bootstrap, reload]);
  return { data, api, reload, connected, loading, error, setError };
}
