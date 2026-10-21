import type { CSSProperties, ReactNode } from "react";

/** Inline SVG motifs and icons from the Ghar mockups. Motifs live here so a region can swap them. */

const stroke = (w: number) => ({
  fill: "none",
  stroke: "currentColor",
  strokeWidth: w,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

function Icon({ size, w = 2, children, style }: { size: number; w?: number; children: ReactNode; style?: CSSProperties }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={style} {...stroke(w)}>
      {children}
    </svg>
  );
}

export const CheckIcon = ({ size = 34, w = 2.8 }: { size?: number; w?: number }) => (
  <Icon size={size} w={w}>
    <path d="M5 12l5 5L20 7" />
  </Icon>
);
export const MicIcon = ({ size = 64 }: { size?: number }) => (
  <Icon size={size}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
    <path d="M12 18v4" />
    <path d="M8 22h8" />
  </Icon>
);
export const ListIcon = ({ size = 28 }: { size?: number }) => (
  <Icon size={size} w={2.4}>
    <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
  </Icon>
);
export const PhoneIcon = ({ size = 28 }: { size?: number }) => (
  <Icon size={size} w={2.4}>
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" />
  </Icon>
);
export const CalendarIcon = ({ size = 32 }: { size?: number }) => (
  <Icon size={size}>
    <rect x="3" y="4" width="18" height="18" rx="2" />
    <path d="M16 2v4M8 2v4M3 10h18" />
  </Icon>
);
export const ClockIcon = ({ size = 76 }: { size?: number }) => (
  <Icon size={size}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icon>
);
export const SpeakerIcon = ({ size = 30 }: { size?: number }) => (
  <Icon size={size} w={2.2}>
    <path d="M11 5L6 9H2v6h4l5 4V5z" />
    <path d="M15.5 8.5a5 5 0 0 1 0 7" />
    <path d="M19 5a10 10 0 0 1 0 14" />
  </Icon>
);
export const LockIcon = ({ size = 22 }: { size?: number }) => (
  <Icon size={size}>
    <rect x="5" y="11" width="14" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </Icon>
);
export const ImageIcon = ({ size = 44 }: { size?: number }) => (
  <Icon size={size} w={1.8}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <circle cx="9" cy="11" r="2" />
    <path d="M21 17l-5-5-8 7" />
  </Icon>
);
export const PillIcon = ({ size = 30 }: { size?: number }) => (
  <Icon size={size}>
    <path d="M10.5 20.5l10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7z" />
    <path d="M8.5 8.5l7 7" />
  </Icon>
);
export const HeartPulseIcon = ({ size = 36 }: { size?: number }) => (
  <Icon size={size}>
    <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z" />
    <path d="M3.5 12h4l2-3 3 6 2-3h6" />
  </Icon>
);
export const CrossIcon = ({ size = 14 }: { size?: number }) => (
  <Icon size={size} w={3}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

export const BellIcon = ({ size = 64 }: { size?: number }) => (
  <svg className="sway" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" fill="var(--ghar-haldi)" stroke="var(--ghar-wood)" strokeWidth="1.4" strokeLinejoin="round" />
    <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" fill="none" stroke="var(--ghar-wood)" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);
export const ThaliIcon = ({ size = 34 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="10" fill="#E9D3A8" />
    <circle cx="12" cy="12" r="6.5" fill="var(--ghar-surface)" stroke="#C9A86A" strokeWidth="1" />
    <circle cx="10" cy="11" r="1.6" fill="var(--ghar-marigold)" />
    <circle cx="13.5" cy="13" r="1.3" fill="var(--ghar-leaf)" />
  </svg>
);
export const SunriseIcon = ({ size = 56 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="14" r="5.5" fill="var(--ghar-haldi)" />
    <path d="M12 4v2.5M4.5 14H2M22 14h-2.5M6.3 8.3 4.6 6.6M17.7 8.3l1.7-1.7" stroke="var(--ghar-marigold)" strokeWidth="2" strokeLinecap="round" />
    <path d="M1 20h22" stroke="var(--ghar-wood)" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
export const MoonIcon = ({ size = 48 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z" fill="var(--ghar-haldi)" />
  </svg>
);

/** The diya = Arjun's presence. `detailed` is the big listening version with an inner flame. */
export function Diya({ size, detailed = false, flame = "var(--ghar-haldi)", label }: { size: number; detailed?: boolean; flame?: string; label?: string }) {
  const a11y = label ? { role: "img", "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...a11y}>
      {detailed ? (
        <>
          <path d="M3 15 Q12 23 21 15 Z" fill="var(--ghar-copper-light)" />
          <path d="M5 15 Q12 19.5 19 15" fill="none" stroke="var(--ghar-wood)" strokeWidth=".8" />
          <path className="flame" d="M12 2.5 C15 7 15.5 9.6 12 13 C8.5 9.6 9 7 12 2.5 Z" fill={flame} />
          <path className="flame" d="M12 6.5 C13.2 8.6 13.3 10 12 11.6 C10.7 10 10.8 8.6 12 6.5 Z" fill="#FFF4D6" />
        </>
      ) : (
        <>
          <path d="M3 15 Q12 23 21 15 Z" fill="var(--ghar-copper)" />
          <path className="flame" d="M12 3 C14.6 7 15 9.4 12 12.5 C9 9.4 9.4 7 12 3 Z" fill={flame} />
        </>
      )}
    </svg>
  );
}

/** Mango-leaf and marigold toran across the top of the morning home screen. */
export function Toran() {
  const leaves = [24, 66, 108, 150, 195, 240, 282, 324, 366];
  const dy = [13, 16, 18, 19, 19, 19, 18, 16, 13];
  return (
    <svg width="100%" height="58" viewBox="0 0 390 58" preserveAspectRatio="xMidYMin slice" aria-hidden="true">
      <path d="M0 10 Q195 26 390 10" fill="none" stroke="var(--ghar-wood)" strokeWidth="2" />
      {leaves.map((x, i) => {
        const y = dy[i] ?? 16;
        return (
        <g key={x}>
          <path d={`M${x} ${y} q-10 18 0 38 q10 -20 0 -38z`} fill={i % 2 === 0 ? "var(--ghar-leaf)" : "var(--ghar-leaf-light)"} />
          {i < leaves.length - 1 && (
            <circle cx={x + 21 + (i === 3 ? 1 : 0)} cy={y + 4} r="7" fill={i % 2 === 1 ? "var(--ghar-marigold)" : "var(--ghar-haldi)"} />
          )}
        </g>
        );
      })}
    </svg>
  );
}
