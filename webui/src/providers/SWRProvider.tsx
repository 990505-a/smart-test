"use client";

import { SWRConfig } from "swr";

export function SWRProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: false,
        dedupingInterval: 5000,
        errorRetryInterval: 3000,
        errorRetryCount: 2,
      }}
    >
      {children}
    </SWRConfig>
  );
}
