"""Fixed reply templates (mr / hi / en). Care-mode replies are templated - never model-generated -
so nothing medical or invented can be spoken. Arjun is an AI and never claims feelings or a body.
"""

from datetime import date, timedelta

from .config import ELDERLINE_NUMBER

R: dict[str, dict[str, str]] = {
    "mr": {
        "ai_disclosure": "मी अर्जुन आहे, एक एआय सहाय्यक. मी माणूस नाही. पण तुमच्या माणसांशी तुमचं बोलणं व्हावं यासाठी मी मदत करतो.",
        "emergency": "हे गंभीर असू शकतं. लगेच ११२ ला फोन करा, किंवा जवळ असलेल्या कोणाला मोठ्याने हाक मारा. मी तुमच्या कुटुंबाला कळवण्याचा प्रयत्न करतो.",
        "distress": f"तुम्ही खूप त्रासात आहात असं वाटतंय. मी इथे ऐकायला आहे. तुम्ही म्हणाल तर मी तुमच्या कुटुंबातील कोणाला फोन लावायला मदत करू का? तसंच सकाळी ८ ते रात्री ८ या वेळेत एल्डरलाइन {ELDERLINE_NUMBER} वर तुम्ही बोलू शकता.",
        "ask_task": "कशाची आठवण ठेवू?",
        "ask_date": "कोणत्या दिवशी? आज की उद्या?",
        "ask_time": "किती वाजता?",
        "ask_ampm": "{hour} वाजता म्हणजे सकाळी की संध्याकाळी?",
        "ask_meal": "दुपारच्या जेवणानंतर की रात्रीच्या जेवणानंतर?",
        "confirm_reminder": "{when} आठवण ठेवू का: {task}? हो किंवा नाही सांगा.",
        "reminder_saved": "ठीक आहे, आठवण नोंदवली.",
        "cancelled": "ठीक आहे, काहीही नोंदवलं नाही.",
        "cancelled_retry": "ठीक आहे, ते रद्द केलं. कृपया पुन्हा सांगा.",
        "yes_or_no": "हो किंवा नाही सांगा.",
        "deliver_reminder": "आठवण: {task}.",
        "deliver_reminder_late": "{when} ची आठवण: {task}.",
        "deliver_medicine": "औषधाची वेळ. {name}. {dose}. वेळ {when}. घेतली का?",
        "med_not_taken_ack": "ठीक आहे, नोंदवलं.",
        "greet": "नमस्कार! मी ऐकतोय. सांगा, काय मदत करू?",
        "hearing_ok": "हो, मला ऐकू येतंय.",
        "time_passed": "ती वेळ निघून गेली आहे. कृपया दुसरी वेळ सांगा.",
        "today_none": "आज तुमच्यासाठी कोणतीही आठवण नाही.",
        "today_list": "आज तुमच्याकडे: {items}.",
        "day_none": "{when} तुमच्यासाठी कोणतीही आठवण नाही.",
        "day_list": "{when} तुमच्याकडे: {items}.",
        "appt_none": "तुमची कोणतीही पुढची भेट नोंदवलेली नाही.",
        "appt_next": "तुमची पुढची भेट: {title}, {when}{place}.",
        "call_family": "{name} यांना फोन करण्याची ही चांगली वेळ आहे. तुम्हाला हवं तेव्हा फोन लावा.",
        "ask_contact": "कोणाला फोन करायचा आहे? {names}",
        "no_contacts": "माझ्याकडे कोणाचाही नंबर नोंदवलेला नाही. तुमच्या काळजीवाहकांना तो जोडायला सांगा.",
        "confirm_caregiver": "मी तुमच्या काळजीवाहकांना कळवू का की तुम्हाला मदत हवी आहे? हो किंवा नाही.",
        "caregiver_done": "ठीक आहे, त्यांना कळवलं आहे.",
        "confirm_share": "ही गोष्ट कुटुंबासोबत शेअर करू का? हो किंवा नाही.",
        "shared_done": "ठीक आहे, ही गोष्ट कुटुंबासोबत शेअर केली.",
        "no_story": "मला शेअर करण्यासाठी किंवा पुसण्यासाठी कोणतीही गोष्ट सापडली नाही.",
        "forgotten": "ठीक आहे, ती गोष्ट पुसून टाकली.",
        "decline": "ठीक आहे. नंतर कधीतरी बोलू.",
        "nothing_pending": "मी काय नोंदवू? कृपया पुन्हा सांगा.",
        "unknown": "मला नीट समजलं नाही. कृपया पुन्हा सांगा.",
        "which_reminder": "कोणती आठवण पूर्ण झाली? {items}",
        "confirm_complete": "{task} झालं असं नोंदवू का? हो किंवा नाही.",
        "completed": "ठीक आहे, ते झालं म्हणून नोंदवलं.",
        "none_to_complete": "आज पूर्ण करायची कोणतीही आठवण दिसत नाही.",
        "ask_save_story": "तुमची गोष्ट मी फक्त तुमच्यासाठी जपून ठेवू का? ती कोणालाही दिसणार नाही. हो किंवा नाही.",
        "story_saved": "ठीक आहे, ती गोष्ट फक्त तुमच्याकडे जपून ठेवली.",
        "error": "काहीतरी अडचण आली. कृपया थोड्या वेळाने पुन्हा सांगा.",
        "opener": "{name}, आज तुम्ही मला {interest} बद्दल काहीतरी शिकवाल का? तुमचा अनुभव सांगा.",
        "when_today": "आज",
        "when_tomorrow": "उद्या",
        "when_day_after": "परवा",
        "at": "{part} {hhmm} वाजता",
        "part_morning": "सकाळी",
        "part_noon": "दुपारी",
        "part_evening": "संध्याकाळी",
        "part_night": "रात्री",
    },
    "hi": {
        "ai_disclosure": "मैं अर्जुन हूँ, एक एआई सहायक। मैं इंसान नहीं हूँ। मैं बस इसलिए हूँ कि आपकी अपनों से बात होती रहे।",
        "emergency": "यह गंभीर हो सकता है। तुरंत 112 पर फोन कीजिए, या पास में जो हो उसे ज़ोर से बुलाइए। मैं आपके परिवार को बताने की कोशिश करता हूँ।",
        "distress": f"लग रहा है आप बहुत परेशान हैं। मैं यहाँ सुनने के लिए हूँ। आप कहें तो मैं आपके परिवार में किसी को फोन लगाने में मदद करूँ? सुबह 8 से रात 8 बजे तक आप एल्डरलाइन {ELDERLINE_NUMBER} पर भी बात कर सकते हैं।",
        "ask_task": "किस चीज़ की याद दिलाऊँ?",
        "ask_date": "किस दिन? आज या कल?",
        "ask_time": "कितने बजे?",
        "ask_ampm": "{hour} बजे यानी सुबह या शाम?",
        "ask_meal": "दोपहर के खाने के बाद या रात के खाने के बाद?",
        "confirm_reminder": "{when} याद दिलाऊँ: {task}? हाँ या नहीं बताइए।",
        "reminder_saved": "ठीक है, याद दिलाने के लिए दर्ज कर लिया।",
        "cancelled": "ठीक है, कुछ दर्ज नहीं किया।",
        "cancelled_retry": "ठीक है, वह रद्द कर दिया। कृपया फिर से बताइए।",
        "yes_or_no": "हाँ या नहीं बताइए।",
        "deliver_reminder": "याद दिलाना: {task}।",
        "deliver_reminder_late": "{when} की याद: {task}।",
        "deliver_medicine": "दवा का समय। {name}। {dose}। समय {when}। ली क्या?",
        "med_not_taken_ack": "ठीक है, दर्ज कर लिया।",
        "greet": "नमस्ते! मैं सुन रहा हूँ। बताइए, क्या मदद करूँ?",
        "hearing_ok": "हाँ, मुझे सुनाई दे रहा है।",
        "time_passed": "वह समय निकल चुका है। कृपया दूसरा समय बताइए।",
        "today_none": "आज आपके लिए कोई रिमाइंडर नहीं है।",
        "today_list": "आज आपके पास: {items}।",
        "day_none": "{when} आपके लिए कोई रिमाइंडर नहीं है।",
        "day_list": "{when} आपके पास: {items}।",
        "appt_none": "आपकी कोई अगली अपॉइंटमेंट दर्ज नहीं है।",
        "appt_next": "आपकी अगली अपॉइंटमेंट: {title}, {when}{place}।",
        "call_family": "{name} को फोन करने के लिए यह अच्छा समय है। जब चाहें फोन लगाइए।",
        "ask_contact": "किसे फोन करना है? {names}",
        "no_contacts": "मेरे पास कोई नंबर दर्ज नहीं है। अपने देखभाल करने वाले से जुड़वाने को कहिए।",
        "confirm_caregiver": "क्या मैं आपके देखभाल करने वाले को बता दूँ कि आपको मदद चाहिए? हाँ या नहीं।",
        "caregiver_done": "ठीक है, उन्हें बता दिया गया है।",
        "confirm_share": "क्या यह कहानी परिवार के साथ साझा करूँ? हाँ या नहीं।",
        "shared_done": "ठीक है, यह कहानी परिवार के साथ साझा कर दी।",
        "no_story": "मुझे साझा करने या मिटाने के लिए कोई कहानी नहीं मिली।",
        "forgotten": "ठीक है, वह कहानी मिटा दी।",
        "decline": "ठीक है। फिर कभी बात करेंगे।",
        "nothing_pending": "मैं क्या दर्ज करूँ? कृपया फिर से बताइए।",
        "unknown": "मुझे ठीक से समझ नहीं आया। कृपया फिर से बताइए।",
        "which_reminder": "कौन सा रिमाइंडर पूरा हुआ? {items}",
        "confirm_complete": "क्या {task} हो गया, ऐसा दर्ज करूँ? हाँ या नहीं।",
        "completed": "ठीक है, उसे पूरा दर्ज कर दिया।",
        "none_to_complete": "आज पूरा करने के लिए कोई रिमाइंडर नहीं दिख रहा।",
        "ask_save_story": "क्या मैं आपकी कहानी सिर्फ आपके लिए सँभालकर रखूँ? किसी को नहीं दिखेगी। हाँ या नहीं।",
        "story_saved": "ठीक है, वह कहानी सिर्फ आपके पास सँभालकर रखी।",
        "error": "कुछ गड़बड़ हो गई। कृपया थोड़ी देर बाद फिर बताइए।",
        "opener": "{name}, आज आप मुझे {interest} के बारे में कुछ सिखाएँगे? अपना अनुभव बताइए।",
        "when_today": "आज",
        "when_tomorrow": "कल",
        "when_day_after": "परसों",
        "at": "{part} {hhmm} बजे",
        "part_morning": "सुबह",
        "part_noon": "दोपहर",
        "part_evening": "शाम",
        "part_night": "रात",
    },
    "en": {
        "ai_disclosure": "I am Arjun, an AI assistant. I am not a person. I am here to help you stay connected with the people who matter to you.",
        "emergency": "This could be serious. Call 112 right now, or call out loudly to someone near you. I will try to let your family know.",
        "distress": f"It sounds like you are going through a very hard time. I am here to listen. If you like, I can help you call someone in your family. You can also talk to Elderline on {ELDERLINE_NUMBER}, between 8 AM and 8 PM.",
        "ask_task": "What should I remind you about?",
        "ask_date": "On which day? Today or tomorrow?",
        "ask_time": "At what time?",
        "ask_ampm": "{hour} o'clock - morning or evening?",
        "ask_meal": "After lunch or after dinner?",
        "confirm_reminder": "Shall I remind you {when}: {task}? Please say yes or no.",
        "reminder_saved": "Okay, the reminder is saved.",
        "cancelled": "Okay, I have not saved anything.",
        "cancelled_retry": "Okay, I cancelled that. Please tell me again.",
        "yes_or_no": "Please say yes or no.",
        "deliver_reminder": "Reminder: {task}.",
        "deliver_reminder_late": "A reminder from {when}: {task}.",
        "deliver_medicine": "Medicine time. {name}. {dose}. Time {when}. Did you take it?",
        "med_not_taken_ack": "Okay, noted.",
        "greet": "Hello! I am listening. How can I help?",
        "hearing_ok": "Yes, I can hear you.",
        "time_passed": "That time has already passed. Please tell me another time.",
        "today_none": "You have no reminders today.",
        "today_list": "Today you have: {items}.",
        "day_none": "You have no reminders {when}.",
        "day_list": "{when} you have: {items}.",
        "appt_none": "You have no upcoming appointment saved.",
        "appt_next": "Your next appointment: {title}, {when}{place}.",
        "call_family": "This is a good time to call {name}. Call whenever you like.",
        "ask_contact": "Whom would you like to call? {names}",
        "no_contacts": "I have no phone numbers saved. Please ask your caregiver to add them.",
        "confirm_caregiver": "Shall I let your caregiver know you need help? Yes or no.",
        "caregiver_done": "Okay, I have let them know.",
        "confirm_share": "Shall I share this story with your family? Yes or no.",
        "shared_done": "Okay, I have shared this story with your family.",
        "no_story": "I could not find a story to share or forget.",
        "forgotten": "Okay, that story is deleted.",
        "decline": "Okay. We can talk another time.",
        "nothing_pending": "What should I save? Please tell me again.",
        "unknown": "I did not understand properly. Please say it again.",
        "which_reminder": "Which reminder is done? {items}",
        "confirm_complete": "Shall I mark {task} as done? Yes or no.",
        "completed": "Okay, marked as done.",
        "none_to_complete": "I do not see any reminder to complete today.",
        "ask_save_story": "Shall I keep your story safe, just for you? Nobody will see it. Yes or no.",
        "story_saved": "Okay, I have kept that story just for you.",
        "error": "Something went wrong. Please try again in a little while.",
        "opener": "{name}, would you teach me something about {interest} today? Tell me about your experience.",
        "when_today": "today",
        "when_tomorrow": "tomorrow",
        "when_day_after": "the day after tomorrow",
        "at": "at {hhmm} {part}",
        "part_morning": "in the morning",
        "part_noon": "in the afternoon",
        "part_evening": "in the evening",
        "part_night": "in the night",
    },
}

# Medicine replies. Medicine name and dose are SQL strings inserted verbatim - never paraphrased,
# translated or generated. Questions about skipping / doubling / lateness / purpose / side effects
# are never answered: Arjun points to the doctor and offers to tell the family.
_MED: dict[str, dict[str, str]] = {
    "mr": {
        "med_none_due": "आत्ता माझ्या नोंदीत कोणतंही औषध घ्यायचं नाही.",
        "med_which": "कोणतं औषध? {names}",
        "confirm_taken": "{name}, {dose} घेतली असं नोंदवू का? हो किंवा नाही.",
        "med_taken_done": "ठीक आहे, घेतली म्हणून नोंदवलं.",
        "confirm_snooze": "१५ मिनिटांनी परत सांगू का? हो किंवा नाही.",
        "med_snoozed_done": "ठीक आहे, १५ मिनिटांनी परत सांगतो.",
        "med_no_more_snooze": "आणखी पुढे ढकलता येत नाही. मी तुमच्या कुटुंबाला कळवू का? हो किंवा नाही.",
        "med_deflect": "हे डॉक्टरांना विचारा. मी तुमच्या काळजीवाहकांना कळवू का? हो किंवा नाही.",
        "med_deflect_named": "हे डॉक्टरांना विचारा. {name}ला कळवू का? हो किंवा नाही.",
        "med_family_sets": "औषधाच्या वेळा तुमचं कुटुंब ठरवतं. मी त्यांना कळवू का? हो किंवा नाही.",
    },
    "hi": {
        "med_none_due": "अभी मेरे रिकॉर्ड में कोई दवा लेने की नहीं है।",
        "med_which": "कौन सी दवा? {names}",
        "confirm_taken": "{name}, {dose} ली, ऐसा दर्ज करूँ? हाँ या नहीं बताइए।",
        "med_taken_done": "ठीक है, ली हुई दर्ज कर ली।",
        "confirm_snooze": "15 मिनट बाद फिर बताऊँ? हाँ या नहीं।",
        "med_snoozed_done": "ठीक है, 15 मिनट बाद फिर बताऊँगा।",
        "med_no_more_snooze": "अब और आगे नहीं टाल सकते। क्या मैं आपके परिवार को बता दूँ? हाँ या नहीं।",
        "med_deflect": "यह डॉक्टर से पूछिए। क्या मैं आपके देखभाल करने वाले को बता दूँ? हाँ या नहीं।",
        "med_deflect_named": "यह डॉक्टर से पूछिए। क्या मैं {name} को बता दूँ? हाँ या नहीं।",
        "med_family_sets": "दवा के समय आपका परिवार तय करता है। क्या मैं उन्हें बता दूँ? हाँ या नहीं।",
    },
    "en": {
        "med_none_due": "I have no medicine due right now in my notes.",
        "med_which": "Which medicine? {names}",
        "confirm_taken": "Shall I note that you took {name}, {dose}? Yes or no.",
        "med_taken_done": "Okay, noted as taken.",
        "confirm_snooze": "Shall I remind you again in 15 minutes? Yes or no.",
        "med_snoozed_done": "Okay, I will remind you again in 15 minutes.",
        "med_no_more_snooze": "I cannot put it off any more. Shall I tell your family? Yes or no.",
        "med_deflect": "Please ask your doctor about that. Shall I tell your caregiver? Yes or no.",
        "med_deflect_named": "Please ask your doctor about that. Shall I tell {name}? Yes or no.",
        "med_family_sets": "Your family sets medicine times. Shall I let them know? Yes or no.",
    },
}
for _lang, _texts in _MED.items():
    R[_lang].update(_texts)

# Time and day guidance. All values come from the household clock and SQL; the weekday and
# month names are fixed tables, so nothing about time is ever generated by a model.
_TIME = {
    "mr": {
        "weekdays": [
            "सोमवार",
            "मंगळवार",
            "बुधवार",
            "गुरुवार",
            "शुक्रवार",
            "शनिवार",
            "रविवार"
        ],
        "months": [
            "जानेवारी",
            "फेब्रुवारी",
            "मार्च",
            "एप्रिल",
            "मे",
            "जून",
            "जुलै",
            "ऑगस्ट",
            "सप्टेंबर",
            "ऑक्टोबर",
            "नोव्हेंबर",
            "डिसेंबर"
        ],
        "time_now": "आत्ता {clock} वाजले आहेत.",
        "date_now": "आज {weekday}, {day} {month} आहे.",
        "next_up": "पुढे {when}: {label}.",
        "next_none": "आज आणखी काही ठरलेलं नाही.",
        "open_now": "आत्ता बाकी आहे: {items}.",
        "meal_lunch": "दुपारचं जेवण",
        "meal_dinner": "रात्रीचं जेवण",
        "wake_label": "उठण्याची वेळ",
        "greet_morning": "शुभ सकाळ",
        "greet_afternoon": "शुभ दुपार",
        "greet_evening": "शुभ संध्याकाळ",
        "greet_night": "शुभ रात्री",
        "briefing": "{greeting}. आज तुमच्याकडे: {items}.",
        "briefing_none": "{greeting}. आज तुमच्यासाठी कोणतीही आठवण नाही."
    },
    "hi": {
        "weekdays": [
            "सोमवार",
            "मंगलवार",
            "बुधवार",
            "गुरुवार",
            "शुक्रवार",
            "शनिवार",
            "रविवार"
        ],
        "months": [
            "जनवरी",
            "फरवरी",
            "मार्च",
            "अप्रैल",
            "मई",
            "जून",
            "जुलाई",
            "अगस्त",
            "सितंबर",
            "अक्टूबर",
            "नवंबर",
            "दिसंबर"
        ],
        "time_now": "अभी {clock} बजे हैं।",
        "date_now": "आज {weekday}, {day} {month} है।",
        "next_up": "आगे {when}: {label}।",
        "next_none": "आज और कुछ तय नहीं है।",
        "open_now": "अभी बाकी है: {items}।",
        "meal_lunch": "दोपहर का खाना",
        "meal_dinner": "रात का खाना",
        "wake_label": "उठने का समय",
        "greet_morning": "सुप्रभात",
        "greet_afternoon": "नमस्कार",
        "greet_evening": "शुभ संध्या",
        "greet_night": "शुभ रात्रि",
        "briefing": "{greeting}। आज आपके पास: {items}।",
        "briefing_none": "{greeting}। आज आपके लिए कोई याद दिलाना नहीं है।"
    },
    "en": {
        "weekdays": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday"
        ],
        "months": [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December"
        ],
        "time_now": "It is {clock} now.",
        "date_now": "Today is {weekday}, {day} {month}.",
        "next_up": "Next, {when}: {label}.",
        "next_none": "Nothing else is planned for today.",
        "open_now": "Still pending: {items}.",
        "meal_lunch": "lunch",
        "meal_dinner": "dinner",
        "wake_label": "wake-up time",
        "greet_morning": "Good morning",
        "greet_afternoon": "Good afternoon",
        "greet_evening": "Good evening",
        "greet_night": "Good night",
        "briefing": "{greeting}. Today you have: {items}.",
        "briefing_none": "{greeting}. You have nothing planned today."
    }
}
for _lang, _texts in _TIME.items():
    R[_lang].update({k: v for k, v in _texts.items() if isinstance(v, str)})
WEEKDAYS = {k: v["weekdays"] for k, v in _TIME.items()}
MONTHS = {k: v["months"] for k, v in _TIME.items()}

# Companion (CHAT) prompts - listen more than talk; no advice, no facts, no memory assertions.
CHAT: dict[str, tuple[str, ...]] = {
    "mr": (
        "अजून सांगा, मी ऐकतोय.",
        "मग पुढे काय झालं?",
        "ते कोणासोबत होतं?",
        "हे तुम्ही तुमच्या माणसांना कधी सांगितलंय का?",
    ),
    "hi": (
        "और बताइए, मैं सुन रहा हूँ।",
        "फिर आगे क्या हुआ?",
        "वह किसके साथ था?",
        "क्या आपने यह अपने लोगों को कभी बताया है?",
    ),
    "en": (
        "Tell me more, I am listening.",
        "And what happened next?",
        "Who was with you then?",
        "Have you ever told this to your own people?",
    ),
}


def lang_or_default(lang: str) -> str:
    return lang if lang in R else "mr"


def say_date(iso: str, today: date, lang: str) -> str:
    d = date.fromisoformat(iso)
    r = R[lang_or_default(lang)]
    if d == today:
        return r["when_today"]
    if d == today + timedelta(days=1):
        return r["when_tomorrow"]
    if d == today + timedelta(days=2):
        return r["when_day_after"]
    return d.strftime("%d/%m")


def say_time(hhmm: str, lang: str) -> str:
    r = R[lang_or_default(lang)]
    h, m = (int(x) for x in hhmm.split(":"))
    if 4 <= h < 12:
        part = r["part_morning"]
    elif 12 <= h < 16:
        part = r["part_noon"]
    elif 16 <= h < 19:
        part = r["part_evening"]
    else:
        part = r["part_night"]
    h12 = h % 12 or 12
    return r["at"].format(part=part, hhmm=f"{h12}:{m:02d}")


def _part_key(h: int) -> str:
    if 4 <= h < 12:
        return "part_morning"
    if 12 <= h < 16:
        return "part_noon"
    if 16 <= h < 19:
        return "part_evening"
    return "part_night"


def say_clock(hhmm: str, lang: str) -> str:
    """Spoken clock reading: 'सकाळी ९:१५' style (en: '9:15 in the morning')."""
    r = R[lang_or_default(lang)]
    h, m = (int(x) for x in hhmm.split(":"))
    part = r[_part_key(h)]
    clock = f"{h % 12 or 12}:{m:02d}"
    return f"{clock} {part}" if lang_or_default(lang) == "en" else f"{part} {clock}"


def say_weekday_date(d: date, lang: str) -> tuple[str, str, str]:
    lg = lang_or_default(lang)
    return WEEKDAYS[lg][d.weekday()], str(d.day), MONTHS[lg][d.month - 1]


def greeting(hour: int, lang: str) -> str:
    r = R[lang_or_default(lang)]
    key = {
        "part_morning": "greet_morning",
        "part_noon": "greet_afternoon",
        "part_evening": "greet_evening",
        "part_night": "greet_night",
    }[_part_key(hour)]
    return r[key]


def item_text(item: dict, lang: str) -> str:  # type: ignore[type-arg]
    """Label for a day item. Task / title / medicine name+dose are SQL text, verbatim."""
    r = R[lang_or_default(lang)]
    kind = item["kind"]
    if kind == "meal":
        return r[f"meal_{item['label']}"]
    if kind == "wake":
        return r["wake_label"]
    if kind == "medicine":
        return f"{item['label']}, {item['detail']}"
    return str(item["label"])
