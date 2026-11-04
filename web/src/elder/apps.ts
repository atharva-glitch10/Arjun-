/** Phone apps the elder page may open (the family approves each one on the dashboard; reasoning only names the id).
 *  The link is built HERE from a fixed table, never taken from the network. Android needs one tap to leave the
 *  browser, so the page shows a big "उघडा" button. Pure and tested. */

export type AppId = "spotify" | "jiosaavn" | "youtube_music" | "google_maps";

interface AppDef {
  label: string;
  pkg: string;
  web: (q: string) => string;
}

const enc = encodeURIComponent;

export const APPS: Record<AppId, AppDef> = {
  spotify: {
    label: "स्पॉटिफाय",
    pkg: "com.spotify.music",
    web: (q) => (q ? `https://open.spotify.com/search/${enc(q)}` : "https://open.spotify.com/"),
  },
  jiosaavn: {
    label: "जिओसावन",
    pkg: "com.jio.media.jiobeats",
    web: (q) => (q ? `https://www.jiosaavn.com/search/${enc(q)}` : "https://www.jiosaavn.com/"),
  },
  youtube_music: {
    label: "यूट्यूब म्युझिक",
    pkg: "com.google.android.apps.youtube.music",
    web: (q) => (q ? `https://music.youtube.com/search?q=${enc(q)}` : "https://music.youtube.com/"),
  },
  google_maps: {
    label: "गूगल मॅप्स",
    pkg: "com.google.android.apps.maps",
    web: (q) => (q ? `https://www.google.com/maps/search/${enc(q)}` : "https://www.google.com/maps"),
  },
};

export const isAppId = (v: string): v is AppId => Object.prototype.hasOwnProperty.call(APPS, v);

/** An Android intent:// link for the app (no browser fallback inside: the page opens the web page itself if the
 *  app did not start, so Arjun's own tab is never replaced), and the plain web page. */
export function appLinks(id: AppId, query: string): { intent: string; web: string } {
  const app = APPS[id];
  const web = app.web(query.trim().slice(0, 100));
  const u = new URL(web);
  const intent = `intent://${u.host}${u.pathname}${u.search}#Intent;scheme=https;package=${app.pkg};end`;
  return { intent, web };
}

export const isAndroid = (ua: string): boolean => /android/i.test(ua);
