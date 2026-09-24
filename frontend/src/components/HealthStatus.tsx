import { useEffect, useState } from "react";

import { getHealth } from "../lib/api";

type ConnectionState = "checking" | "connected" | "unavailable";

export function HealthStatus(): React.JSX.Element {
  const [connection, setConnection] = useState<ConnectionState>("checking");

  useEffect(() => {
    let isActive = true;

    void getHealth()
      .then(() => {
        if (isActive) {
          setConnection("connected");
        }
      })
      .catch(() => {
        if (isActive) {
          setConnection("unavailable");
        }
      });

    return () => {
      isActive = false;
    };
  }, []);

  const labels: Record<ConnectionState, string> = {
    checking: "Checking API",
    connected: "API connected",
    unavailable: "API unavailable",
  };
  const colors: Record<ConnectionState, string> = {
    checking: "bg-amber-400",
    connected: "bg-emerald-500",
    unavailable: "bg-rose-500",
  };

  return (
    <p aria-live="polite" className="flex items-center gap-2 text-sm text-slate-600">
      <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${colors[connection]}`} />
      {labels[connection]}
    </p>
  );
}
