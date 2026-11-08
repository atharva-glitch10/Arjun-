"""Build the 80-case synthetic turn-quality corpus. No production conversation is included."""
import json
from pathlib import Path

GROUPS = {
    "mr-IN": [
        ("आज वांग्याचं भरीत केलं", "answer_topic", "food"), ("राहुल जेवला असेल का", "answer_topic", "family"),
        ("भूक लागली आहे", "answer_topic", "food"), ("यूट्यूबवर भजन लाव", "answer_topic", "media"),
        ("मला पुण्याला जायचं होतं", "specific_clarify", "travel"), ("बागेत फुलं आली", "answer_topic", "garden"),
        ("डॉक्टरची भेट उद्या आहे का", "answer_topic", "appointment"), ("औषधाबद्दल मला विचारायचं आहे", "answer_topic", "medicine_no_advice"),
    ],
    "hi-IN": [
        ("आज मैंने बैंगन का भरता बनाया", "answer_topic", "food"), ("राहुल ने खाना खाया होगा क्या", "answer_topic", "family"),
        ("मुझे भूख लगी है", "answer_topic", "food"), ("यूट्यूब पर भजन चलाइए", "answer_topic", "media"),
        ("मुझे पुणे जाना था", "specific_clarify", "travel"), ("बगीचे में फूल आए हैं", "answer_topic", "garden"),
        ("डॉक्टर की मुलाकात कल है क्या", "answer_topic", "appointment"), ("दवा को लेकर एक सवाल है", "answer_topic", "medicine_no_advice"),
    ],
    "hi-Latn": [
        ("Aaj baingan ka bharta banaya", "answer_topic", "hinglish_food"), ("Rahul ne khana khaya hoga kya", "answer_topic", "hinglish_family"),
        ("Mujhe bhook lagi hai", "answer_topic", "hinglish_food"), ("YouTube pe bhajan chalao", "answer_topic", "hinglish_media"),
        ("Mujhe Pune jaana tha", "specific_clarify", "hinglish_travel"), ("Garden mein phool aaye hain", "answer_topic", "hinglish_garden"),
        ("Doctor ki appointment kal hai kya", "answer_topic", "hinglish_appointment"), ("Dawai ke baare mein poochna hai", "answer_topic", "hinglish_medicine"),
    ],
    "ta-IN": [
        ("இன்று கத்திரிக்காய் உணவு செய்தேன்", "answer_topic", "food"), ("ராகுல் சாப்பிட்டிருப்பாரா", "answer_topic", "family"),
        ("எனக்குப் பசிக்கிறது", "answer_topic", "food"), ("யூடியூபில் பக்திப் பாடல் போடு", "answer_topic", "media"),
        ("நான் புனே செல்ல வேண்டும்", "specific_clarify", "travel"), ("தோட்டத்தில் பூக்கள் வந்தன", "answer_topic", "garden"),
        ("மருத்துவர் சந்திப்பு நாளையா", "answer_topic", "appointment"), ("மருந்தைப் பற்றி கேட்க வேண்டும்", "answer_topic", "medicine_no_advice"),
    ],
    "kn-IN": [
        ("ಇಂದು ಬದನೆಕಾಯಿ ಪಲ್ಯ ಮಾಡಿದೆ", "answer_topic", "food"), ("ರಾಹುಲ್ ಊಟ ಮಾಡಿರಬಹುದಾ", "answer_topic", "family"),
        ("ನನಗೆ ಹಸಿವಾಗಿದೆ", "answer_topic", "food"), ("ಯೂಟ್ಯೂಬ್‌ನಲ್ಲಿ ಭಜನೆ ಹಾಕಿ", "answer_topic", "media"),
        ("ನಾನು ಪುಣೆಗೆ ಹೋಗಬೇಕಿತ್ತು", "specific_clarify", "travel"), ("ತೋಟದಲ್ಲಿ ಹೂವು ಬಿಟ್ಟಿವೆ", "answer_topic", "garden"),
        ("ವೈದ್ಯರ ಭೇಟಿ ನಾಳೆಯೇ", "answer_topic", "appointment"), ("ಔಷಧದ ಬಗ್ಗೆ ಕೇಳಬೇಕಿದೆ", "answer_topic", "medicine_no_advice"),
    ],
    "bn-IN": [
        ("আজ বেগুনের পদ রান্না করেছি", "answer_topic", "food"), ("রাহুল কি খেয়ে নিয়েছে", "answer_topic", "family"),
        ("আমার খিদে পেয়েছে", "answer_topic", "food"), ("ইউটিউবে ভজন চালাও", "answer_topic", "media"),
        ("আমার পুনে যাওয়ার কথা ছিল", "specific_clarify", "travel"), ("বাগানে ফুল ফুটেছে", "answer_topic", "garden"),
        ("ডাক্তারের দেখা কি কাল", "answer_topic", "appointment"), ("ওষুধ নিয়ে জানতে চাই", "answer_topic", "medicine_no_advice"),
    ],
    "gu-IN": [
        ("આજે રીંગણનો ઓળો બનાવ્યો", "answer_topic", "food"), ("રાહુલે જમ્યું હશે કે", "answer_topic", "family"),
        ("મને ભૂખ લાગી છે", "answer_topic", "food"), ("યૂટ્યુબ પર ભજન વગાડો", "answer_topic", "media"),
        ("મારે પુણે જવું હતું", "specific_clarify", "travel"), ("બગીચામાં ફૂલ ખીલ્યાં", "answer_topic", "garden"),
        ("ડૉક્ટરની મુલાકાત કાલે છે", "answer_topic", "appointment"), ("દવા વિશે પૂછવું છે", "answer_topic", "medicine_no_advice"),
    ],
    "pa-IN": [
        ("ਅੱਜ ਬੈਂਗਣ ਦੀ ਸਬਜ਼ੀ ਬਣਾਈ", "answer_topic", "food"), ("ਰਾਹੁਲ ਨੇ ਖਾਣਾ ਖਾ ਲਿਆ ਹੋਵੇਗਾ", "answer_topic", "family"),
        ("ਮੈਨੂੰ ਭੁੱਖ ਲੱਗੀ ਹੈ", "answer_topic", "food"), ("ਯੂਟਿਊਬ ਤੇ ਭਜਨ ਚਲਾਓ", "answer_topic", "media"),
        ("ਮੈਂ ਪੁਣੇ ਜਾਣਾ ਸੀ", "specific_clarify", "travel"), ("ਬਾਗ ਵਿੱਚ ਫੁੱਲ ਖਿੜੇ ਹਨ", "answer_topic", "garden"),
        ("ਡਾਕਟਰ ਨੂੰ ਕੱਲ੍ਹ ਮਿਲਣਾ ਹੈ", "answer_topic", "appointment"), ("ਦਵਾਈ ਬਾਰੇ ਪੁੱਛਣਾ ਹੈ", "answer_topic", "medicine_no_advice"),
    ],
    "te-IN": [
        ("ఈరోజు వంకాయ కూర చేశాను", "answer_topic", "food"), ("రాహుల్ భోజనం చేసి ఉంటాడా", "answer_topic", "family"),
        ("నాకు ఆకలిగా ఉంది", "answer_topic", "food"), ("యూట్యూబ్‌లో భజన పెట్టు", "answer_topic", "media"),
        ("నేను పుణెకు వెళ్లాల్సింది", "specific_clarify", "travel"), ("తోటలో పూలు పూశాయి", "answer_topic", "garden"),
        ("డాక్టర్ అపాయింట్మెంట్ రేపేనా", "answer_topic", "appointment"), ("మందుల గురించి అడగాలి", "answer_topic", "medicine_no_advice"),
    ],
    "ml-IN": [
        ("ഇന്ന് വഴുതനങ്ങ കറി ഉണ്ടാക്കി", "answer_topic", "food"), ("രാഹുൽ ഭക്ഷണം കഴിച്ചിട്ടുണ്ടാകുമോ", "answer_topic", "family"),
        ("എനിക്ക് വിശക്കുന്നു", "answer_topic", "food"), ("യൂട്യൂബിൽ ഭജൻ ഇടൂ", "answer_topic", "media"),
        ("എനിക്ക് പൂനെയിൽ പോകണമായിരുന്നു", "specific_clarify", "travel"), ("തോട്ടത്തിൽ പൂക്കൾ വിരിഞ്ഞു", "answer_topic", "garden"),
        ("ഡോക്ടറെ കാണുന്നത് നാളെയാണോ", "answer_topic", "appointment"), ("മരുന്നിനെക്കുറിച്ച് ചോദിക്കണം", "answer_topic", "medicine_no_advice"),
    ],
}

for lang, samples in GROUPS.items():
    assert len(samples) >= 6, lang
cases = []
for lang, samples in GROUPS.items():
    for i, (text, behavior, topic) in enumerate(samples[:6], 1):
        cases.append({"id": f"logic-{lang}-{i:02}", "text": text, "language_code": lang,
                      "expected_behavior": behavior, "topic": topic, "tags": [lang, topic]})

# Five anonymized variants of patterns found in the synthetic turnlog audit.
cases.extend([
    {"id": "audit-01", "text": "[video_call_stopped]", "language_code": "mr-IN", "expected_behavior": "silent", "topic": "system_event", "tags": ["marker", "audit"]},
    {"id": "audit-02", "text": "YouTube kholo", "language_code": "hi-Latn", "expected_behavior": "answer_topic", "topic": "youtube_open", "tags": ["audit", "action"]},
    {"id": "audit-03", "text": "thamb thamb thamb", "language_code": "mr-IN", "expected_behavior": "specific_clarify", "topic": "stop_or_continue", "tags": ["audit", "stt_noisy"]},
    {"id": "audit-04", "text": "कलेक्शनमध्ये", "language_code": "mr-IN", "expected_behavior": "specific_clarify", "topic": "collection", "tags": ["audit", "cut_off"]},
    {"id": "audit-05", "text": "एप्रिलमध्ये रिकामं आहे सगळं", "language_code": "mr-IN", "expected_behavior": "specific_clarify", "topic": "calendar", "tags": ["audit", "stt_noisy"]},
])

# Memory-dependent continuity; ordered last to avoid contaminating the topic checks above.
cases.extend([
    {"id": "memory-01", "text": "राहुलने काय आणलं होतं?", "language_code": "mr-IN", "expected_behavior": "answer_topic", "topic": "memory", "setup_turns": ["राहुल काल आंबे घेऊन आला होता"], "tags": ["memory"]},
    {"id": "memory-02", "text": "I told you I made what today?", "language_code": "hi-Latn", "expected_behavior": "answer_topic", "topic": "memory", "setup_turns": ["आज मी पुरणपोळी केली"], "tags": ["memory", "code_mix"]},
    {"id": "memory-03", "text": "அவர் எங்கே போனார்?", "language_code": "ta-IN", "expected_behavior": "answer_topic", "topic": "memory", "setup_turns": ["ரவி கடைக்குச் சென்றார்"], "tags": ["memory"]},
    {"id": "memory-04", "text": "ನಾನು ಏನು ಮಾಡಿದೆ ಎಂದು ಹೇಳಿದ್ದೆ?", "language_code": "kn-IN", "expected_behavior": "answer_topic", "topic": "memory", "setup_turns": ["ನಾನು ಇಂದು ಹೂವಿನ ಗಿಡ ನೆಟ್ಟೆ"], "tags": ["memory"]},
    {"id": "memory-05", "text": "আমি কী রান্না করেছিলাম?", "language_code": "bn-IN", "expected_behavior": "answer_topic", "topic": "memory", "setup_turns": ["আমি আজ ডাল রান্না করেছি"], "tags": ["memory"]},
])

# Additional realistic noisy/cut-off/code-mixed cases to reach eighty total.
extras = [
    ("भजन लाव ना आणि", "mr-IN", "specific_clarify", "media_cutoff", "cut_off"),
    ("kal Rahul ka call karna tha but he was busy", "hi-Latn", "answer_topic", "code_mix_family", "code_mix"),
    ("மருந்து பற்றி ஒரு கேள்வி", "ta-IN", "answer_topic", "medicine_no_advice", "medical_safe"),
    ("ಇವತ್ತು ತುಂಬಾ ಚೆನ್ನಾಗಿದೆ ಅಲ್ವಾ", "kn-IN", "answer_topic", "chat", "normal"),
    ("রাহুল আজ বাড়ি আসবে", "bn-IN", "answer_topic", "family", "normal"),
    ("मला औषधाबद्दल प्रश्न आहे", "mr-IN", "answer_topic", "medicine_no_advice", "medical_safe"),
    ("मेरे कैलेंडर में अप्रैल खाली है", "hi-IN", "specific_clarify", "calendar", "stt_noisy"),
    ("कलेक्शनमध्ये", "mr-IN", "specific_clarify", "collection", "cut_off"),
    ("Marathi-English mix: आज माझा mood छान आहे", "mr-IN", "answer_topic", "code_mix", "code_mix"),
    ("ஆமா, அந்த நாளைக்கு போகணும்", "ta-IN", "specific_clarify", "cut_off", "cut_off"),
]
for i, (text, lang, behavior, topic, tag) in enumerate(extras, 1):
    cases.append({"id": f"extra-{i:02}", "text": text, "language_code": lang,
                  "expected_behavior": behavior, "topic": topic, "tags": [tag]})

assert len(cases) == 80, len(cases)
out = Path(__file__).with_name("logic_eval.jsonl")
out.write_text("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases), encoding="utf-8")
print(f"wrote {len(cases)} synthetic cases")
