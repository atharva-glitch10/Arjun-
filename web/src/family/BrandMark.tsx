/** The Arjun mark and wordmark for the family header ("listens with care"). */
export function BrandMark() {
  return (
    <div className="brand">
      <div className="mark">
        <svg width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden="true">
          <path d="M7 10a9 9 0 0 0 0 12" stroke="#F5A623" strokeWidth="2" strokeLinecap="round" />
          <path d="M4 7a13 13 0 0 0 0 18" stroke="#F5A623" strokeWidth="1.6" strokeLinecap="round" opacity="0.6" />
          <path d="M25 10a9 9 0 0 1 0 12" stroke="#F5A623" strokeWidth="2" strokeLinecap="round" />
          <path d="M28 7a13 13 0 0 1 0 18" stroke="#F5A623" strokeWidth="1.6" strokeLinecap="round" opacity="0.6" />
          <path d="M16 22s-5-3-5-6.5a2.5 2.5 0 0 1 5-1 2.5 2.5 0 0 1 5 1C21 19 16 22 16 22Z" fill="#ffffff" />
        </svg>
      </div>
      <div>
        <span className="name">Arjun</span>
        <span className="tagline">listens with care</span>
      </div>
    </div>
  );
}
