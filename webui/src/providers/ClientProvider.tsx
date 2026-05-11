"use client";

import React, { createContext, useContext, useMemo } from "react";
import { Client } from "@langchain/langgraph-sdk";

const ClientContext = createContext<Client | null>(null);

export function ClientProvider({
  children,
  deploymentUrl,
  apiKey,
}: {
  children: React.ReactNode;
  deploymentUrl: string;
  apiKey?: string;
}) {
  const client = useMemo(
    () => new Client({ apiUrl: deploymentUrl, apiKey }),
    [deploymentUrl, apiKey]
  );
  return (
    <ClientContext.Provider value={client}>{children}</ClientContext.Provider>
  );
}

export function useClient(): Client {
  const client = useContext(ClientContext);
  if (!client)
    throw new Error("useClient must be used within ClientProvider");
  return client;
}
