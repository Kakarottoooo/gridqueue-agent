import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GridQueue Agent",
  description: "Public-data interconnection queue monitoring and risk briefs"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

