/** Words for the family login / sign-up / account bar, in Marathi, Hindi and English (deadline 2026-11-10).
 *  Kept apart from elder/strings.ts on purpose: that table needs ten languages per key and these screens are for family
 *  members, who use mr / hi / en. The other seven languages fall back to English. */
export type AuthLang = "mr" | "hi" | "en";
export const AUTH_LANGS: [AuthLang, string][] = [["mr", "मराठी"], ["hi", "हिंदी"], ["en", "English"]];

type Row = [mr: string, hi: string, en: string];
const T = {
  title: ["Arjun · कुटुंब", "Arjun · परिवार", "Arjun · Family"],
  login_sub: ["तुमची व्यक्ती कशी आहे ते पाहण्यासाठी लॉग इन करा.", "अपनों का हाल देखने के लिए लॉग इन करें।", "Log in to see how your loved one is doing."],
  signup_sub: ["कुटुंबाचं खातं तयार करा.", "परिवार का खाता बनाएँ।", "Create a family account."],
  your_name: ["तुमचं नाव", "आपका नाम", "Your name"],
  email: ["ईमेल", "ईमेल", "Email"],
  password: ["पासवर्ड", "पासवर्ड", "Password"],
  password_hint: ["(किमान १० अक्षरं)", "(कम से कम 10 अक्षर)", "(at least 10 characters)"],
  signup_code: ["नोंदणी कोड", "साइन-अप कोड", "Sign-up code"],
  signup_code_hint: ["(अर्जुन सुरू करणाऱ्यांकडून घ्या)", "(अर्जुन शुरू करने वाले से लें)", "(ask the person who set Arjun up)"],
  login: ["लॉग इन", "लॉग इन", "Log in"],
  create: ["खातं तयार करा", "खाता बनाएँ", "Create account"],
  to_signup: ["नवीन आहात? खातं तयार करा", "नए हैं? खाता बनाएँ", "New here? Create an account"],
  to_login: ["आधीच खातं आहे? लॉग इन करा", "पहले से खाता है? लॉग इन करें", "Already have an account? Log in"],
  err_wrong: ["ईमेल किंवा पासवर्ड चुकीचा आहे.", "ईमेल या पासवर्ड गलत है।", "Wrong email or password."],
  err_many: ["खूप प्रयत्न झाले, एक मिनिट थांबा.", "बहुत कोशिशें हो गईं, एक मिनट रुकें।", "Too many attempts, wait a minute."],
  err_code: ["नोंदणी कोड चुकीचा किंवा राहिला आहे.", "साइन-अप कोड गलत है या छूट गया है।", "Wrong or missing sign-up code."],
  err_closed: ["नोंदणी बंद आहे. अर्जुन सुरू करणाऱ्यांकडे कोड मागा.", "साइन-अप बंद है। अर्जुन शुरू करने वाले से कोड माँगें।", "Sign-up is closed. Ask the person who set Arjun up for the code."],
  err_exists: ["या ईमेलचं खातं आधीच आहे. लॉग इन करा.", "इस ईमेल का खाता पहले से है। लॉग इन करें।", "An account with this email already exists. Log in instead."],
  err_check: ["ईमेल तपासा आणि किमान १० अक्षरांचा पासवर्ड वापरा.", "ईमेल जाँचें और कम से कम 10 अक्षर का पासवर्ड रखें।", "Check the email, and use a password of at least 10 characters."],
  err_net: ["अर्जुनशी संपर्क होत नाही. तो सुरू आहे का?", "अर्जुन से संपर्क नहीं हो पा रहा। क्या वह चालू है?", "Could not reach Arjun. Is it running?"],
  elder: ["आजी/आजोबा", "बुज़ुर्ग", "Elder"],
  add_elder: ["+ व्यक्ती जोडा", "+ बुज़ुर्ग जोड़ें", "+ Add elder"],
  add: ["जोडा", "जोड़ें", "Add"],
  cancel: ["रद्द करा", "रद्द करें", "Cancel"],
  logout: ["लॉग आउट", "लॉग आउट", "Log out"],
  add_title: ["तुम्ही ज्यांची काळजी घेता त्यांना जोडा", "जिनकी आप देखभाल करते हैं उन्हें जोड़ें", "Add the person you care for"],
  add_help: ["वर \"व्यक्ती जोडा\" वापरा. एकापेक्षा जास्त जोडता येतात.", "ऊपर \"बुज़ुर्ग जोड़ें\" दबाएँ। एक से ज़्यादा जोड़ सकते हैं।", "Use \"Add elder\" above. You can add more than one."],
  elder_name: ["व्यक्तीचं नाव", "बुज़ुर्ग का नाम", "Elder's name"],
  name_ph: ["नाव (उदा. हीराबाई)", "नाम (जैसे हीराबाई)", "Name (e.g. हीराबाई)"],
  language: ["भाषा", "भाषा", "Language"],
  add_failed: ["जोडता आलं नाही", "जोड़ नहीं सके", "Could not add"],
} satisfies Record<string, Row>;

export type AuthKey = keyof typeof T;
export const AUTH_KEYS = Object.keys(T) as AuthKey[];

export function at(key: AuthKey, lang: AuthLang): string {
  const row = T[key] as Row;
  return row[["mr", "hi", "en"].indexOf(lang)] || row[2];
}

const STORE = "arjun_auth_lang";

/** Her saved choice, else the browser language (Marathi / Hindi), else English. */
export function detectAuthLang(): AuthLang {
  try {
    const saved = localStorage.getItem(STORE);
    if (saved === "mr" || saved === "hi" || saved === "en") return saved;
  } catch {
    // storage blocked
  }
  const nav = typeof navigator !== "undefined" ? (navigator.language || "").toLowerCase() : "";
  return nav.startsWith("mr") ? "mr" : nav.startsWith("hi") ? "hi" : "en";
}

export function saveAuthLang(lang: AuthLang): void {
  try {
    localStorage.setItem(STORE, lang);
  } catch {
    // ignore
  }
}

/** The line to show for a failed login / sign-up, from the error text the api helper throws ("403: sign-up is closed"). */
export function authErrorKey(message: string, mode: "login" | "signup"): AuthKey {
  if (message.startsWith("429")) return "err_many";
  if (message.startsWith("401")) return "err_wrong";
  if (message.startsWith("409")) return "err_exists";
  if (message.startsWith("422")) return "err_check";
  if (message.startsWith("403") && mode === "signup") return message.includes("closed") ? "err_closed" : "err_code";
  return "err_net";
}
