import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Folio — Document search",
  description:
    "Search your PDF by words, meaning, and visual content. Read the matching pages in context.",
  icons: { icon: "/folio.svg" },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
