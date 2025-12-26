import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "GuqinAuto",
    template: "%s · GuqinAuto",
  },
  description: "简谱→古琴减字谱自动编配与双谱面编辑器（前端）",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

