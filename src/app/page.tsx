import { AppLayout } from "@/components/layout/AppLayout";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";

// FVS-001 foundation-slice placeholder — not the real F-001 Home page
// (that content belongs to FVS-022). This just proves the shell boots.
export default function Home() {
  return (
    <AppLayout header={<Header />} footer={<Footer />}>
      <h1 className="text-h1 font-bold text-text-primary">
        Bekaa3D — Engineered Grade 3D Solutions
      </h1>
      <p className="text-body text-text-secondary">
        This is the FVS-001 frontend foundation slice. The real Bekaa3D home
        page arrives in a later slice.
      </p>
    </AppLayout>
  );
}
