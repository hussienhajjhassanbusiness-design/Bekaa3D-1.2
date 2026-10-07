export interface DownloadButtonProps {
  // Already-authorized destination from a future adapter — this
  // component never derives, constructs, or rewrites a URL from
  // storage metadata (#SECURITY-AUTHORIZED-DOWNLOAD-HREF). Never a
  // storage path/S3 URL/private filesystem path/X-Accel internal path.
  authorizedHref: string;
  // Full context required — never inferred. "Download" alone is not
  // an acceptable accessible name; callers must supply e.g.
  // "Download Dragon STL".
  accessibleLabel: string;
}

// #ARCHITECTURE-NATIVE-STL-DOWNLOAD
//
// MUST be a real <a href>, never a JS click-handler that fetches. The
// backend streams the file through nginx X-Accel-Redirect and supports
// HTTP Range — native browser navigation preserves Range/resume
// behavior and large-file streaming performance; a fetch() → blob() →
// URL.createObjectURL() path would silently break all of that. Future
// contributors must NOT refactor this into a blob-fetch "improvement."
//
// No `download` attribute: the backend's own Content-Disposition
// header stays authoritative over the saved filename, not a client
// guess. No `target="_blank"`: same-tab native navigation is preferred
// unless a confirmed product requirement says otherwise.
export function DownloadButton({ authorizedHref, accessibleLabel }: DownloadButtonProps) {
  return (
    <a href={authorizedHref} className="inline-block rounded-md bg-brand-dark-green px-4 py-2 text-text-on-brand">
      {accessibleLabel}
    </a>
  );
}
