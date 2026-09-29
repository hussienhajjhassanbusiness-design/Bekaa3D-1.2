// FVS-001 foundation-slice placeholder — not the real F-001 Home page
// (that content belongs to FVS-022). This just proves the shell boots.
// The AppLayout/Header/Footer shell itself is owned by the root layout
// (FVS001-T14) — this file owns only its own page content.
export default function Home() {
  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">
        Bekaa3D — Engineered Grade 3D Solutions
      </h1>
      <p className="text-body text-text-secondary">
        This is the FVS-001 frontend foundation slice. The real Bekaa3D home
        page arrives in a later slice.
      </p>
    </>
  );
}
