import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "FlightLens · Theo dõi & dự báo chuyến bay",
  description: "Mẫu giao diện tổng quan và dự báo độ trễ chuyến bay Mỹ.",
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="vi"><body>{children}</body></html>;
}
