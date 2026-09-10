import type { CSSProperties } from "react";

interface BrandLogoProps {
  size?: number;
  variant?: "tile" | "glyph";
  className?: string;
  style?: CSSProperties;
}

export function BrandLogo({ size = 32, variant = "tile", className, style }: BrandLogoProps) {
  const idPrefix = "kn-mono-logo";

  if (variant === "glyph") {
    return (
      <div
        className={className}
        style={{
          width: size,
          height: size,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          ...style,
        }}
      >
        <svg
          width={size}
          height={size}
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          style={{ display: "block" }}
        >
          {/* Minimalist Monochrome Shield Silhouette */}
          <path
            d="M 16 3 C 21.5 3 27 5.5 27 5.5 C 27 17.5 22 25 16 29 C 10 25 5 17.5 5 5.5 C 5 5.5 10.5 3 16 3 Z"
            fill="currentColor"
          />
          {/* Negative Space Precision Checkmark */}
          <path
            d="M 11.5 15.5 L 14.5 18.5 L 21 11.5"
            stroke="var(--stage-bg)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    );
  }

  // Default: Pure Monochrome Obsidian Tile (Deep Space Black & Brushed Titanium Silver)
  const borderRadius = Math.round((size * 9) / 36);

  return (
    <div
      className={className}
      style={{
        width: size,
        height: size,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        boxShadow: "0 4px 14px rgba(0, 0, 0, 0.28)",
        borderRadius: `${borderRadius}px`,
        ...style,
      }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 36 36"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ display: "block" }}
      >
        <defs>
          {/* Pure Monochrome Obsidian Background: Deep Space Gray to Jet Black */}
          <linearGradient id={`${idPrefix}-bg`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#26262a" />
            <stop offset="100%" stopColor="#0a0a0c" />
          </linearGradient>

          {/* Top Specular Reflection Light Rim */}
          <linearGradient id={`${idPrefix}-rim`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.38" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0.06" />
          </linearGradient>

          {/* Titanium Left Facet (Brilliant Silver Highlight) */}
          <linearGradient id={`${idPrefix}-facet-l`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#d4d4d8" />
          </linearGradient>

          {/* Titanium Right Facet (Deep Graphite Shading) */}
          <linearGradient id={`${idPrefix}-facet-r`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a1a1aa" />
            <stop offset="100%" stopColor="#71717a" />
          </linearGradient>

          {/* Neutral Depth Shadow */}
          <filter id={`${idPrefix}-shadow`} x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="1.2" stdDeviation="1.2" floodColor="#000000" floodOpacity="0.45" />
          </filter>
        </defs>

        {/* Squircle Base Tile (Obsidian Black) */}
        <rect width="36" height="36" rx="9" fill={`url(#${idPrefix}-bg)`} />
        <rect x="0.5" y="0.5" width="35" height="35" rx="8.5" stroke={`url(#${idPrefix}-rim)`} strokeWidth="1" />

        {/* Monochrome 3D Titanium Shield with Certified Checkmark */}
        <g filter={`url(#${idPrefix}-shadow)`}>
          {/* Left Facet (Bright Specular Titanium) */}
          <path
            d="M 18 7.5 C 13.5 7.5 9 9.2 9 9.2 C 9 18.8 13.2 25.2 18 28.5 L 18 7.5 Z"
            fill={`url(#${idPrefix}-facet-l)`}
          />
          {/* Right Facet (Graphite Shaded Titanium) */}
          <path
            d="M 18 7.5 C 22.5 7.5 27 9.2 27 9.2 C 27 18.8 22.8 25.2 18 28.5 L 18 7.5 Z"
            fill={`url(#${idPrefix}-facet-r)`}
          />
          {/* Shield Precision Silver Rim */}
          <path
            d="M 18 7.5 C 22.5 7.5 27 9.2 27 9.2 C 27 18.8 22.8 25.2 18 28.5 C 13.2 25.2 9 18.8 9 9.2 C 9 9.2 13.5 7.5 18 7.5 Z"
            stroke="#ffffff"
            strokeOpacity="0.85"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
          {/* Center Vertical Crease */}
          <line x1="18" y1="7.5" x2="18" y2="28.5" stroke="#ffffff" strokeOpacity="0.5" strokeWidth="0.75" />

          {/* Pure Arctic White Certified Precision Checkmark */}
          <path
            d="M 14.5 17.5 L 17 20 L 22.5 13.5"
            stroke="#ffffff"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
      </svg>
    </div>
  );
}
