// Vitest stand-in for `next/font/local`. In a Next build the loader call is
// replaced at compile time by the SWC font transform; the package's runtime
// module is empty, so importing it under Vitest would yield `undefined`.
// The stub returns the same shape (className, variable, style) with empty
// values: unit tests check structure and behaviour, never font files.
interface LocalFontResult {
  className: string;
  variable: string;
  style: { fontFamily: string };
}

export default function localFont(): LocalFontResult {
  return { className: "", variable: "", style: { fontFamily: "" } };
}
