// A simplified, low-opacity silhouette of the Capitol dome — decorative only.
export default function CapitolWatermark({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 200 120"
      className={className}
      fill="currentColor"
      aria-hidden="true"
    >
      <rect x="0" y="104" width="200" height="4" />
      <rect x="14" y="70" width="8" height="34" />
      <rect x="34" y="70" width="8" height="34" />
      <rect x="54" y="70" width="8" height="34" />
      <rect x="138" y="70" width="8" height="34" />
      <rect x="158" y="70" width="8" height="34" />
      <rect x="178" y="70" width="8" height="34" />
      <rect x="10" y="62" width="180" height="8" />
      <rect x="70" y="52" width="60" height="18" />
      <rect x="80" y="38" width="40" height="14" />
      <path d="M88 38 Q88 14 100 8 Q112 14 112 38 Z" />
      <rect x="97" y="0" width="6" height="10" />
      <circle cx="100" cy="0" r="3" />
    </svg>
  );
}
