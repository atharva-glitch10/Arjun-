/** "Apps and links" on the family dashboard: what the elder may open by voice. Pure helpers (tested). */
import type { AppLink, Contact } from "../api";

export const KIND_LABELS: Record<AppLink["kind"], string> = {
  youtube_playlist: "YouTube playlist (songs, bhajans)",
  youtube_video: "YouTube video",
  youtube_query: "YouTube search (first match plays)",
  youtube_channel_live: "Live news channel (YouTube)",
  rss: "News feed (read aloud)",
  whatsapp: "WhatsApp (a contact)",
  link: "Web link",
};

/** What to open to TEST an entry on this device. WhatsApp uses the contact's number (synthetic in the demo). */
export function testUrl(link: AppLink, contacts: Contact[]): string | null {
  switch (link.kind) {
    case "youtube_video":
      return `https://www.youtube.com/watch?v=${link.value}`;
    case "youtube_playlist":
      return `https://www.youtube.com/playlist?list=${link.value}`;
    case "youtube_channel_live":
      return `https://www.youtube.com/channel/${link.value}/live`;
    case "youtube_query":
      return `https://www.youtube.com/results?search_query=${encodeURIComponent(link.value)}`;
    case "rss":
    case "link":
      return link.value.startsWith("https://") ? link.value : null;
    case "whatsapp": {
      const phone = contacts.find((c) => String(c.id) === link.value)?.phone ?? "";
      let digits = phone.replace(/\D/g, "");
      if (digits.length === 10) digits = `91${digits}`;
      return digits ? `https://wa.me/${digits}` : null;
    }
    default:
      return null;
  }
}

/** The host of a link or feed that is not on the known list but the family approved: shown with a warning. */
export const warning = (link: AppLink): string =>
  link.other_host ? "This website is not on the known list. Only keep it if you trust it." : "";
