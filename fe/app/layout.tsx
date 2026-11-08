import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
});

export const metadata: Metadata = {
  title: "FlightLens · Giám sát Radar, Phân cụm K-Means & Dự báo Chuyến bay",
  description: "Hệ thống quan sát không lưu thời gian thực, phân cụm sân bay K-Means và dự báo độ trễ chuyến bay Hoa Kỳ.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={plexSans.variable}>
      <body>{children}</body>
    </html>
  );
}
