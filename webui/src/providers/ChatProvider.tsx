"use client";

import React, { createContext, useContext } from "react";
import { useChat } from "@/app/hooks/useChat";
import { Assistant } from "@langchain/langgraph-sdk";

export type ChatContextType = ReturnType<typeof useChat>;

const ChatContext = createContext<ChatContextType | null>(null);

interface ChatProviderProps {
  children: React.ReactNode;
  activeAssistant: Assistant | null;
  onHistoryRevalidate?: () => void;
}

export function ChatProvider({
  children,
  activeAssistant,
  onHistoryRevalidate,
}: ChatProviderProps) {
  const chat = useChat({
    assistantId: activeAssistant?.assistant_id || "",
    onHistoryRevalidate,
  });

  return <ChatContext.Provider value={chat}>{children}</ChatContext.Provider>;
}

export function useChatContext(): ChatContextType {
  const ctx = useContext(ChatContext);
  if (!ctx) {
    throw new Error("useChatContext must be used within a ChatProvider");
  }
  return ctx;
}
