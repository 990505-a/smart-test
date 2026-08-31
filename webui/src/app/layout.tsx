import { NuqsAdapter } from "nuqs/adapters/next/app";
import { ThemeProvider } from "@/providers/ThemeProvider";
import { SWRProvider } from "@/providers/SWRProvider";
import { AuthProvider } from "@/providers/AuthProvider";
import { AppShell } from "@/app/components/AppShell";
import { Toaster } from "sonner";
import "./globals.css";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="font-sans" suppressHydrationWarning>
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
          <SWRProvider>
            <AuthProvider>
              <NuqsAdapter>
                <AppShell>{children}</AppShell>
              </NuqsAdapter>
            </AuthProvider>
          </SWRProvider>
          <Toaster position="top-center" />
        </ThemeProvider>
      </body>
    </html>
  );
}
