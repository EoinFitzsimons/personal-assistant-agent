import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Day Planner — personal assistant",
  description: "Plans tomorrow from your work apps and wearables",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
