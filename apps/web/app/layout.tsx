import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./styles.css";

export const metadata: Metadata = {
  title: "Tactiqo — AI Operations",
  description: "مساعد عمليات مؤسسي مدعوم بالمعرفة والأدوات والموافقات البشرية.",
};

type RootLayoutProps = Readonly<{ children: ReactNode }>;

export default function RootLayout({ children }: RootLayoutProps) {
  return <html lang="ar" dir="rtl"><body>{children}</body></html>;
}
