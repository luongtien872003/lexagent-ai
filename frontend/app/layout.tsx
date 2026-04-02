import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title:       "LexAgent — Legal Intelligence",
  description: "Trợ lý pháp lý thông minh cho Bộ luật Lao động Việt Nam",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;1,400&family=Inter:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="font-sans text-base text-ink-0 bg-bg-base">
        {children}
      </body>
    </html>
  );
}
