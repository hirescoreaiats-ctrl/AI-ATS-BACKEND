import { useEffect, useRef, useState } from "react";

const API_BASE = (import.meta.env.VITE_API_BASE || runtimeApiBase()).replace(/\/$/, "");

function runtimeApiBase() {
  const isLocalFrontend =
    window.location.protocol === "file:" ||
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";
  return isLocalFrontend ? "http://127.0.0.1:8000" : window.location.origin;
}

export function useWorkspaceSocket(workspaceId = "default") {
  const [lastMessage, setLastMessage] = useState(null);
  const socketRef = useRef(null);

  useEffect(() => {
    const wsBase = API_BASE.replace(/^http/, "ws");
    const socket = new WebSocket(`${wsBase}/api/v1/realtime/workspace/${workspaceId}`);
    socketRef.current = socket;
    socket.onmessage = (event) => {
      try {
        setLastMessage(JSON.parse(event.data));
      } catch {
        setLastMessage({ type: "message", payload: event.data });
      }
    };
    return () => socket.close();
  }, [workspaceId]);

  function publish(message) {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    }
  }

  return { lastMessage, publish };
}
