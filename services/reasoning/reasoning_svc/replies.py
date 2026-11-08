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
        "lonely": "एकटं वाटणं खूप जड असतं. मी इथे ऐकायला आहे. {names} यांच्याशी फोनवर बोलायला आवडेल का? नाहीतर मला तुमच्या दिवसाबद्दल सांगा.",
        "lonely_no_contacts": "एकटं वाटणं खूप जड असतं. मी इथे ऐकायला आहे. मला तुमच्या दिवसाबद्दल सांगा. आणि घरच्यांना एक फोन केलात तर बरं वाटेल.",
        "symptom_noted": "घरच्यांना कळवलं आहे.",
        "web_filler": "बघतो…",
        "web_none": "आत्ता माहिती मिळाली नाही.",
        "web_health": "काळजी करू नका. हे डॉक्टरांना विचारा.",
        "web_city": "कोणत्या गावाचं हवामान सांगू?",
        "web_city_offer": " हे तुमचं गाव म्हणून ठेवू का?",
        "web_city_saved": "ठीक आहे, गाव ठेवलं.",
        "web_city_declined": "ठीक आहे, ठेवलं नाही.",
        "web_source": "{src} नुसार: {answer}",
        "web_hold": "थोडा वेळ लागतोय…",
        "symptom_not_noted": "हे घरच्यांना किंवा डॉक्टरांना नक्की सांगा.",
        "no_contacts": "माझ्याकडे कोणाचाही नंबर नोंदवलेला नाही. तुमच्या काळजीवाहकांना तो जोडायला सांगा.",
        "confirm_caregiver": "मी तुमच्या काळजीवाहकांना कळवू का की तुम्हाला मदत हवी आहे? हो किंवा नाही.",
        "caregiver_done": "ठीक आहे, त्यांना कळवलं आहे.",
        "confirm_share": "ही गोष्ट कुटुंबासोबत शेअर करू का? हो किंवा नाही.",
        "shared_done": "ठीक आहे, ही गोष्ट कुटुंबासोबत शेअर केली.",
        "no_story": "मला शेअर करण्यासाठी किंवा पुसण्यासाठी कोणतीही गोष्ट सापडली नाही.",
        "forgotten": "ठीक आहे, ती गोष्ट पुसून टाकली.",
        "decline": "ठीक आहे. नंतर कधीतरी बोलू.",
        "nothing_pending": "मी काय नोंदवू? कृपया पुन्हा सांगा.",
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
        "lonely": "अकेलापन बहुत भारी लगता है। मैं यहाँ सुनने के लिए हूँ। क्या आप {names} से फोन पर बात करना चाहेंगे? या मुझे अपने दिन के बारे में बताइए।",
        "lonely_no_contacts": "अकेलापन बहुत भारी लगता है। मैं यहाँ सुनने के लिए हूँ। मुझे अपने दिन के बारे में बताइए। और घर पर किसी को एक फोन कर लें तो अच्छा लगेगा।",
        "symptom_noted": "घरवालों को बता दिया है।",
        "web_filler": "देखता हूँ…",
        "web_none": "अभी जानकारी नहीं मिली।",
        "web_health": "चिंता मत कीजिए। यह डॉक्टर से पूछिए।",
        "web_city": "किस शहर का मौसम बताऊँ?",
        "web_city_offer": " इसे आपका शहर मानकर रख लूँ?",
        "web_city_saved": "ठीक है, शहर रख लिया।",
        "web_city_declined": "ठीक है, नहीं रखा।",
        "web_source": "{src} के अनुसार: {answer}",
        "web_hold": "थोड़ा समय लग रहा है…",
        "symptom_not_noted": "यह घरवालों या डॉक्टर को ज़रूर बताइए।",
        "no_contacts": "मेरे पास कोई नंबर दर्ज नहीं है। अपने देखभाल करने वाले से जुड़वाने को कहिए।",
        "confirm_caregiver": "क्या मैं आपके देखभाल करने वाले को बता दूँ कि आपको मदद चाहिए? हाँ या नहीं।",
        "caregiver_done": "ठीक है, उन्हें बता दिया गया है।",
        "confirm_share": "क्या यह कहानी परिवार के साथ साझा करूँ? हाँ या नहीं।",
        "shared_done": "ठीक है, यह कहानी परिवार के साथ साझा कर दी।",
        "no_story": "मुझे साझा करने या मिटाने के लिए कोई कहानी नहीं मिली।",
        "forgotten": "ठीक है, वह कहानी मिटा दी।",
        "decline": "ठीक है। फिर कभी बात करेंगे।",
        "nothing_pending": "मैं क्या दर्ज करूँ? कृपया फिर से बताइए।",
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
        "lonely": "Feeling lonely is hard. I am here to listen. Would you like to talk to {names} on the phone? Or tell me about your day.",
        "lonely_no_contacts": "Feeling lonely is hard. I am here to listen. Tell me about your day. A phone call to someone in your family may help too.",
        "symptom_noted": "I have told your family.",
        "web_filler": "Let me check…",
        "web_none": "I could not get that information right now.",
        "web_health": "Please do not worry. Do ask your doctor about this.",
        "web_city": "Which city's weather should I check?",
        "web_city_offer": " Shall I keep this as your city?",
        "web_city_saved": "Okay, I have saved your city.",
        "web_city_declined": "Okay, I did not save it.",
        "web_source": "According to {src}: {answer}",
        "web_hold": "This is taking a little while…",
        "symptom_not_noted": "Please do tell your family or your doctor.",
        "no_contacts": "I have no phone numbers saved. Please ask your caregiver to add them.",
        "confirm_caregiver": "Shall I let your caregiver know you need help? Yes or no.",
        "caregiver_done": "Okay, I have let them know.",
        "confirm_share": "Shall I share this story with your family? Yes or no.",
        "shared_done": "Okay, I have shared this story with your family.",
        "no_story": "I could not find a story to share or forget.",
        "forgotten": "Okay, that story is deleted.",
        "decline": "Okay. We can talk another time.",
        "nothing_pending": "What should I save? Please tell me again.",
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
        "meal_breakfast": "नाश्ता",
        "meal_lunch": "दुपारचं जेवण",
        "meal_snack": "संध्याकाळचा नाश्ता",
        "meal_dinner": "रात्रीचं जेवण",
        "walk_label": "फिरायला जाण्याची वेळ",
        "bp_label": "बीपी तपासण्याची वेळ",
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
        "meal_breakfast": "नाश्ता",
        "meal_lunch": "दोपहर का खाना",
        "meal_snack": "शाम का नाश्ता",
        "meal_dinner": "रात का खाना",
        "walk_label": "सैर पर जाने का समय",
        "bp_label": "बीपी जाँचने का समय",
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
        "meal_breakfast": "breakfast",
        "meal_lunch": "lunch",
        "meal_snack": "evening snack",
        "meal_dinner": "dinner",
        "walk_label": "time for your walk",
        "bp_label": "time to check your BP",
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
    if lang_or_default(lang) == "en":  # "7:00 PM", not "7:00 in the night" (live run 2026-11-09)
        return r["at"].format(part="AM" if h < 12 else "PM", hhmm=f"{h12}:{m:02d}")
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
    if kind in ("walk", "bp"):
        return r[f"{kind}_label"]
    if kind == "medicine":
        return f"{item['label']}, {item['detail']}"
    return str(item["label"])


# ---- No-question mode (default since 2026-10-31): Arjun acts at once, says what it did in one line, and
# "नको / चुकलं" within a few minutes undoes it. Only missing details (which day? what time?) are still asked.
# "Told the family" always means the family DASHBOARD (no call/SMS exists): the wording never claims more.
AUTO: dict[str, dict[str, str]] = {
    "mr": {
        "auto_reminder": "ठेवली: {when}, {task}. बदलायचं असेल तर 'नको' म्हणा.",
        "auto_complete": "{task} झालं, नोंदवलं.",
        "auto_caregiver": "{family} निरोप पाठवला आहे.",
        "auto_share": "ही गोष्ट घरच्यांसोबत शेअर केली.",
        "auto_taken": "{name} घेतली, नोंदवलं.",
        "auto_snooze": "ठीक आहे, १५ मिनिटांनी परत सांगतो.",
        "auto_no_more_snooze": "आणखी पुढे ढकलता येत नाही. घरच्यांच्या स्क्रीनवर कळवलं आहे.",
        "auto_med_deflect": "हे डॉक्टरांना विचारा. घरच्यांच्या स्क्रीनवर कळवलं आहे.",
        "auto_med_deflect_named": "हे डॉक्टरांना विचारा. {name}ला स्क्रीनवर कळवलं आहे.",
        "auto_med_family_sets": "औषधाच्या वेळा तुमचं कुटुंब ठरवतं. त्यांना स्क्रीनवर कळवलं आहे.",
        "deliver_medicine_auto": "औषधाची वेळ. {name}. {dose}. वेळ {when}.",
        "undone": "ठीक आहे, ते रद्द केलं.",
        "undone_retry": "रद्द केलं. आता पुन्हा सांगा.",
        "undone_help": "ठीक आहे. घरच्यांना कळवलं की आता मदत नको.",
        "ok_ack": "ठीक आहे.",
    },
    "hi": {
        "auto_reminder": "रख लिया: {when}, {task}. बदलना हो तो 'नहीं' कहिए।",
        "auto_complete": "{task} हो गया, दर्ज कर लिया।",
        "auto_caregiver": "{family} संदेश भेज दिया है।",
        "auto_share": "यह बात घरवालों के साथ साझा कर दी।",
        "auto_taken": "{name} ली, दर्ज कर लिया।",
        "auto_snooze": "ठीक है, 15 मिनट बाद फिर बताऊँगा।",
        "auto_no_more_snooze": "अब और आगे नहीं टाल सकते। घरवालों की स्क्रीन पर बता दिया है।",
        "auto_med_deflect": "यह डॉक्टर से पूछिए। घरवालों की स्क्रीन पर बता दिया है।",
        "auto_med_deflect_named": "यह डॉक्टर से पूछिए। {name} को स्क्रीन पर बता दिया है।",
        "auto_med_family_sets": "दवा के समय आपका परिवार तय करता है। उन्हें स्क्रीन पर बता दिया है।",
        "deliver_medicine_auto": "दवा का समय। {name}. {dose}. समय {when}.",
        "undone": "ठीक है, वह रद्द कर दिया।",
        "undone_retry": "रद्द कर दिया। अब फिर से बताइए।",
        "undone_help": "ठीक है। घरवालों को बता दिया कि अब मदद नहीं चाहिए।",
        "ok_ack": "ठीक है।",
    },
    "en": {
        "auto_reminder": "Saved: {when}, {task}. Say 'no' if that is wrong.",
        "auto_complete": "Noted, {task} is done.",
        "auto_caregiver": "I have sent {family} a message.",
        "auto_share": "I have shared this story with your family.",
        "auto_taken": "Noted, you took {name}.",
        "auto_snooze": "Okay, I will remind you again in 15 minutes.",
        "auto_no_more_snooze": "I cannot put it off any more. I have told your family on their screen.",
        "auto_med_deflect": "Please ask your doctor about that. I have told your family on their screen.",
        "auto_med_deflect_named": "Please ask your doctor about that. I have told {name} on the screen.",
        "auto_med_family_sets": "Your family sets medicine times. I have told them on their screen.",
        "deliver_medicine_auto": "Medicine time. {name}. {dose}. Time {when}.",
        "undone": "Okay, I have cancelled that.",
        "undone_retry": "Cancelled. Please say it again.",
        "undone_help": "Okay. I have told your family you do not need help now.",
        "ok_ack": "Okay.",
    },
}
for _lang, _keys in AUTO.items():
    R[_lang].update(_keys)

# Meal / walk / BP check-ins. Prompts and answers are fixed templates; the answer is the elder's own
# self-report. Nothing here scores, judges or advises.
_CHECKIN: dict[str, dict[str, str]] = {
    "mr": {
        "checkin_prompt_breakfast": "नाश्त्याची वेळ. नाश्ता झाला का?",
        "checkin_prompt_lunch": "दुपारच्या जेवणाची वेळ. जेवण झालं का?",
        "checkin_prompt_snack": "संध्याकाळच्या नाश्त्याची वेळ. नाश्ता झाला का?",
        "checkin_prompt_walk": "फिरायला जाण्याची वेळ. फिरायला गेलात का?",
        "checkin_prompt_bp": "बीपी तपासण्याची वेळ.",
        "checkin_done_breakfast": "ठीक आहे, नाश्ता झाला असं नोंदवलं.",
        "checkin_done_lunch": "ठीक आहे, दुपारचं जेवण झालं असं नोंदवलं.",
        "checkin_done_snack": "ठीक आहे, संध्याकाळचा नाश्ता झाला असं नोंदवलं.",
        "checkin_done_walk": "ठीक आहे, फिरायला गेल्याचं नोंदवलं.",
        "checkin_done_bp": "ठीक आहे, बीपी तपासणी झाली असं नोंदवलं.",
        "checkin_skipped_breakfast": "ठीक आहे, नाश्ता नाही झाला असं नोंदवलं.",
        "checkin_skipped_lunch": "ठीक आहे, दुपारचं जेवण नाही झालं असं नोंदवलं.",
        "checkin_skipped_snack": "ठीक आहे, संध्याकाळचा नाश्ता नाही झाला असं नोंदवलं.",
        "checkin_skipped_walk": "ठीक आहे, फिरायला जाता आलं नाही असं नोंदवलं.",
        "checkin_skipped_bp": "ठीक आहे, बीपी तपासणी नाही झाली असं नोंदवलं.",
        "checkin_class_today": "आज {when} {title} आहे.",
        "checkin_again": "पुन्हा आठवण: {prompt}",
    },
    "hi": {
        "checkin_prompt_breakfast": "नाश्ते का समय। नाश्ता हो गया?",
        "checkin_prompt_lunch": "दोपहर के खाने का समय। खाना हो गया?",
        "checkin_prompt_snack": "शाम के नाश्ते का समय। नाश्ता हो गया?",
        "checkin_prompt_walk": "सैर पर जाने का समय। सैर पर गए?",
        "checkin_prompt_bp": "बीपी जाँचने का समय।",
        "checkin_done_breakfast": "ठीक है, नाश्ता हो गया, दर्ज कर लिया।",
        "checkin_done_lunch": "ठीक है, दोपहर का खाना हो गया, दर्ज कर लिया।",
        "checkin_done_snack": "ठीक है, शाम का नाश्ता हो गया, दर्ज कर लिया।",
        "checkin_done_walk": "ठीक है, सैर पर गए, दर्ज कर लिया।",
        "checkin_done_bp": "ठीक है, बीपी जाँच हो गई, दर्ज कर लिया।",
        "checkin_skipped_breakfast": "ठीक है, नाश्ता नहीं हुआ, दर्ज कर लिया।",
        "checkin_skipped_lunch": "ठीक है, दोपहर का खाना नहीं हुआ, दर्ज कर लिया।",
        "checkin_skipped_snack": "ठीक है, शाम का नाश्ता नहीं हुआ, दर्ज कर लिया।",
        "checkin_skipped_walk": "ठीक है, सैर पर नहीं जा सके, दर्ज कर लिया।",
        "checkin_skipped_bp": "ठीक है, बीपी जाँच नहीं हुई, दर्ज कर लिया।",
        "checkin_class_today": "आज {when} {title} है।",
        "checkin_again": "फिर याद दिलाता हूँ: {prompt}",
    },
    "en": {
        "checkin_prompt_breakfast": "Time for breakfast. Have you had breakfast?",
        "checkin_prompt_lunch": "Time for lunch. Have you had lunch?",
        "checkin_prompt_snack": "Time for your evening snack. Have you had it?",
        "checkin_prompt_walk": "Time for your walk. Did you go for your walk?",
        "checkin_prompt_bp": "Time to check your BP.",
        "checkin_done_breakfast": "Okay, noted that you had breakfast.",
        "checkin_done_lunch": "Okay, noted that you had lunch.",
        "checkin_done_snack": "Okay, noted that you had your snack.",
        "checkin_done_walk": "Okay, noted that you went for your walk.",
        "checkin_done_bp": "Okay, noted that you checked your BP.",
        "checkin_skipped_breakfast": "Okay, noted that you did not have breakfast.",
        "checkin_skipped_lunch": "Okay, noted that you did not have lunch.",
        "checkin_skipped_snack": "Okay, noted that you did not have your snack.",
        "checkin_skipped_walk": "Okay, noted that you could not go for your walk.",
        "checkin_skipped_bp": "Okay, noted that you did not check your BP.",
        "checkin_class_today": "You have {title} today {when}.",
        "checkin_again": "A reminder again: {prompt}",
    },
}
for _lang, _texts in _CHECKIN.items():
    R[_lang].update(_texts)

# Proactive day check-ins (2026-11-03). ONE short question, and a reply of at most one sentence. The wording is
# fixed (never LLM-written); {name}, {interest}, {title}, {when} and {him} come from SQL. Nothing here advises,
# diagnoses, scores or claims a feeling (boundary 4). A nudge exists only for a meal.
_DAY: dict[str, dict[str, str]] = {
    "mr": {
        "checkin_prompt_sleep": "नमस्कार {name}, रात्री झोप नीट लागली का?",
        "checkin_prompt_breakfast": "नाश्ता झाला का?",
        "checkin_prompt_lunch": "दुपारचं जेवण झालं का? काय केलं होतं?",
        "checkin_prompt_walk": "आज थोडं फिरणं झालं का?",
        "checkin_prompt_dinner": "रात्रीचं जेवण झालं का? आजचा दिवस कसा गेला?",
        "checkin_prompt_bp": "बीपी तपासायची वेळ झाली. आकडे सांगा — वरचा आणि खालचा.",
        "checkin_prompt_sugar": "शुगर तपासायची वेळ झाली. किती आली ते सांगा.",
        "checkin_prompt_sugar_after": "जेवणानंतरची शुगर तपासायची वेळ झाली. किती आली ते सांगा.",
        "checkin_prompt_water": "थोडं पाणी प्यायलं का?",
        "checkin_prompt_wellbeing": "दुपार कशी चालली आहे? काही त्रास?",
        "checkin_prompt_reflection": "आजचा दिवस कसा गेला?",
        "checkin_prompt_night": "उद्या {next} आहे. शुभ रात्री!",
        "checkin_prompt_company": "बोलूया का थोडं?",
        "checkin_prompt_interest": "आज {interest} ऐकायचं आहे का?",
        "checkin_prompt_home": "आज {name}शी बोलणं झालं का?",
        "checkin_prompt_appt": "आज {when} {title} आहे, लक्षात आहे ना?",
        "checkin_done_sleep": "बरं झालं.",
        "checkin_skipped_sleep": "ठीक आहे, नोंद केली.",
        "checkin_done_breakfast": "छान!",
        "checkin_skipped_breakfast": "ठीक आहे. लवकर काहीतरी खाऊन घ्या.",
        "checkin_done_lunch": "छान!",
        "checkin_skipped_lunch": "ठीक आहे. लवकर काहीतरी खाऊन घ्या.",
        "checkin_done_snack": "छान!",
        "checkin_skipped_snack": "ठीक आहे.",
        "checkin_done_dinner": "छान!",
        "checkin_skipped_dinner": "ठीक आहे. थोडं काहीतरी खाऊन घ्या.",
        "checkin_done_walk": "छान!",
        "checkin_skipped_walk": "ठीक आहे.",
        "checkin_done_bp": "बरं, आकडे नोंदवले.",
        "checkin_skipped_bp": "ठीक आहे, बीपी तपासणी नाही झाली असं नोंदवलं.",
        "checkin_done_sugar": "बरं, आकडे नोंदवले.",
        "checkin_skipped_sugar": "ठीक आहे, शुगर तपासणी नाही झाली असं नोंदवलं.",
        "checkin_done_sugar_after": "बरं, आकडे नोंदवले.",
        "checkin_skipped_sugar_after": "ठीक आहे, शुगर तपासणी नाही झाली असं नोंदवलं.",
        "checkin_done_water": "छान.",
        "checkin_skipped_water": "ठीक आहे, नोंद केली.",
        "checkin_done_wellbeing": "बरं झालं.",
        "checkin_skipped_wellbeing": "ठीक आहे. जास्त त्रास असेल तर सांगा.",
        "checkin_done_reflection": "छान.",
        "checkin_skipped_reflection": "ठीक आहे.",
        "checkin_done_night": "शुभ रात्री!",
        "checkin_skipped_night": "ठीक आहे. शुभ रात्री!",
        "checkin_done_company": "छान.",
        "checkin_skipped_company": "ठीक आहे.",
        "checkin_done_interest": "ठीक आहे.",
        "checkin_skipped_interest": "ठीक आहे.",
        "checkin_done_home": "छान!",
        "checkin_skipped_home": "{him} निरोप पाठवू का?",
        "checkin_done_appt": "बरं झालं.",
        "checkin_skipped_appt": "ठीक आहे. आज {when} {title} आहे.",
        "checkin_offer_sent": "ठीक आहे.",
        "checkin_offer_no": "ठीक आहे.",
        "checkin_offer_message": "She has not spoken to {name} today; please call her.",
    },
    "hi": {
        "checkin_prompt_sleep": "नमस्ते {name}, रात को नींद ठीक से आई?",
        "checkin_prompt_breakfast": "नाश्ता हो गया?",
        "checkin_prompt_lunch": "दोपहर का खाना हो गया? क्या खाया था?",
        "checkin_prompt_snack": "शाम का नाश्ता हो गया? क्या खाया?",
        "checkin_prompt_walk": "आज थोड़ा टहलना हुआ?",
        "checkin_prompt_dinner": "रात का खाना हो गया? आज का दिन कैसा रहा?",
        "checkin_prompt_bp": "बीपी जाँचने का समय। ऊपर और नीचे के आंकड़े बताइए।",
        "checkin_prompt_sugar": "शुगर जाँचने का समय। कितनी आई, बताइए।",
        "checkin_prompt_sugar_after": "खाने के बाद की शुगर जाँचने का समय। कितनी आई, बताइए।",
        "checkin_prompt_water": "थोड़ा पानी पिया?",
        "checkin_prompt_wellbeing": "दोपहर कैसी चल रही है? कोई तकलीफ़?",
        "checkin_prompt_reflection": "आज का दिन कैसा रहा?",
        "checkin_prompt_night": "कल {next} है। शुभ रात्रि!",
        "checkin_prompt_company": "थोड़ी बात करें?",
        "checkin_prompt_interest": "आज {interest} सुनना है?",
        "checkin_prompt_home": "आज {name} से बात हुई?",
        "checkin_prompt_appt": "आज {when} {title} है, याद है ना?",
        "checkin_done_sleep": "अच्छा हुआ।",
        "checkin_skipped_sleep": "ठीक है, दर्ज कर लिया।",
        "checkin_done_breakfast": "बढ़िया!",
        "checkin_skipped_breakfast": "ठीक है। जल्दी कुछ खा लीजिए।",
        "checkin_done_lunch": "बढ़िया!",
        "checkin_skipped_lunch": "ठीक है। जल्दी कुछ खा लीजिए।",
        "checkin_done_snack": "बढ़िया!",
        "checkin_skipped_snack": "ठीक है।",
        "checkin_done_dinner": "बढ़िया!",
        "checkin_skipped_dinner": "ठीक है। थोड़ा कुछ खा लीजिए।",
        "checkin_done_walk": "बढ़िया!",
        "checkin_skipped_walk": "ठीक है।",
        "checkin_done_bp": "ठीक है, आंकड़े दर्ज कर लिए।",
        "checkin_skipped_bp": "ठीक है, बीपी जाँच नहीं हुई, दर्ज कर लिया।",
        "checkin_done_sugar": "ठीक है, आंकड़े दर्ज कर लिए।",
        "checkin_skipped_sugar": "ठीक है, शुगर जाँच नहीं हुई, दर्ज कर लिया।",
        "checkin_done_sugar_after": "ठीक है, आंकड़े दर्ज कर लिए।",
        "checkin_skipped_sugar_after": "ठीक है, शुगर जाँच नहीं हुई, दर्ज कर लिया।",
        "checkin_done_water": "अच्छा।",
        "checkin_skipped_water": "ठीक है, दर्ज कर लिया।",
        "checkin_done_wellbeing": "अच्छा हुआ।",
        "checkin_skipped_wellbeing": "ठीक है। ज़्यादा तकलीफ़ हो तो बताइए।",
        "checkin_done_reflection": "अच्छा।",
        "checkin_skipped_reflection": "ठीक है।",
        "checkin_done_night": "शुभ रात्रि!",
        "checkin_skipped_night": "ठीक है। शुभ रात्रि!",
        "checkin_done_company": "अच्छा।",
        "checkin_skipped_company": "ठीक है।",
        "checkin_done_interest": "ठीक है।",
        "checkin_skipped_interest": "ठीक है।",
        "checkin_done_home": "बढ़िया!",
        "checkin_skipped_home": "{him} संदेश भेज दूँ?",
        "checkin_done_appt": "अच्छा हुआ।",
        "checkin_skipped_appt": "ठीक है। आज {when} {title} है।",
        "checkin_offer_sent": "ठीक है।",
        "checkin_offer_no": "ठीक है।",
        "checkin_offer_message": "She has not spoken to {name} today; please call her.",
    },
    "en": {
        "checkin_prompt_sleep": "Good morning {name}, did you sleep well last night?",
        "checkin_prompt_breakfast": "Have you had breakfast?",
        "checkin_prompt_lunch": "Have you had lunch? What did you have?",
        "checkin_prompt_snack": "Have you had your evening snack? What did you have?",
        "checkin_prompt_walk": "Did you get a little walk today?",
        "checkin_prompt_dinner": "Have you had dinner? How was your day?",
        "checkin_prompt_bp": "Time to check your BP. Please tell me the upper and lower numbers.",
        "checkin_prompt_sugar": "Time to check your sugar. Please tell me the number.",
        "checkin_prompt_sugar_after": "Time for your after-meal sugar check. Please tell me the number.",
        "checkin_prompt_water": "Did you drink a little water?",
        "checkin_prompt_wellbeing": "How is the afternoon going? Any discomfort?",
        "checkin_prompt_reflection": "How did the day go?",
        "checkin_prompt_night": "Tomorrow is {next}. Good night!",
        "checkin_prompt_company": "Shall we talk a little?",
        "checkin_prompt_interest": "Would you like to listen to {interest} today?",
        "checkin_prompt_home": "Did you speak with {name} today?",
        "checkin_prompt_appt": "You have {title} today {when}. Do you remember?",
        "checkin_done_sleep": "Good.",
        "checkin_skipped_sleep": "Okay, noted.",
        "checkin_done_breakfast": "Nice!",
        "checkin_skipped_breakfast": "Okay. Please have something soon.",
        "checkin_done_lunch": "Nice!",
        "checkin_skipped_lunch": "Okay. Please have something soon.",
        "checkin_done_snack": "Nice!",
        "checkin_skipped_snack": "Okay.",
        "checkin_done_dinner": "Nice!",
        "checkin_skipped_dinner": "Okay. Please have a little something.",
        "checkin_done_walk": "Nice!",
        "checkin_skipped_walk": "Okay.",
        "checkin_done_bp": "Okay, noted the numbers.",
        "checkin_skipped_bp": "Okay, noted that you did not check your BP.",
        "checkin_done_sugar": "Okay, noted the numbers.",
        "checkin_skipped_sugar": "Okay, noted that you did not check your sugar.",
        "checkin_done_sugar_after": "Okay, noted the numbers.",
        "checkin_skipped_sugar_after": "Okay, noted that you did not check your sugar.",
        "checkin_done_water": "Good.",
        "checkin_skipped_water": "Okay, noted.",
        "checkin_done_wellbeing": "Good to hear.",
        "checkin_skipped_wellbeing": "Okay. Please tell me if it gets worse.",
        "checkin_done_reflection": "Good.",
        "checkin_skipped_reflection": "Okay.",
        "checkin_done_night": "Good night!",
        "checkin_skipped_night": "Okay. Good night!",
        "checkin_done_company": "Good.",
        "checkin_skipped_company": "Okay.",
        "checkin_done_interest": "Okay.",
        "checkin_skipped_interest": "Okay.",
        "checkin_done_home": "Nice!",
        "checkin_skipped_home": "Shall I send {him} a message?",
        "checkin_done_appt": "Good.",
        "checkin_skipped_appt": "Okay. You have {title} today {when}.",
        "checkin_offer_sent": "Okay.",
        "checkin_offer_no": "Okay.",
        "checkin_offer_message": "She has not spoken to {name} today; please call her.",
    },
}
for _lang, _texts in _DAY.items():
    R[_lang].update(_texts)

# "{him}" in the offer: the pronoun for the person named, by the family-set relation. Marathi takes "ला".
PRONOUN: dict[str, dict[str, str]] = {
    "mr": {"m": "त्याला", "f": "तिला", "n": "त्यांना"},
    "hi": {"m": "उन्हें", "f": "उन्हें", "n": "उन्हें"},
    "en": {"m": "him", "f": "her", "n": "them"},
}
_MALE = ("मुलगा", "नातू", "भाऊ", "नवरा", "पती", "वडील", "जावई", "son", "grandson", "brother")
_FEMALE = ("मुलगी", "नात", "सून", "बहीण", "पत्नी", "आई", "daughter", "granddaughter", "sister")


def pronoun_for(relation: str, lang: str) -> str:
    """त्याला / तिला / त्यांना for the relation the family set. Unknown or mixed: the plural, never a guess."""
    rel = relation.strip().lower()
    key = "n"
    if any(rel == w for w in _MALE):
        key = "m"
    elif any(rel == w for w in _FEMALE):
        key = "f"
    return PRONOUN[lang_or_default(lang)][key]

# A spoken BP reading: the SAME numbers back, fixed wording. Never good / bad / high / low / normal, never
# advice (boundary 7). {reading} is already in the elder's script, e.g. "१३२ बाय ८६".
_READING: dict[str, dict[str, str]] = {
    "mr": {"bp_recorded": "बीपी {reading} नोंदवलं."},
    "hi": {"bp_recorded": "बीपी {reading} दर्ज कर लिया।"},
    "en": {"bp_recorded": "BP {reading}, noted."},
}
for _lang, _texts in _READING.items():
    R[_lang].update(_texts)


# ---- memory commands ("हे लक्षात ठेव" / "हे विसरून जा"): one fixed line each, no question ------------------------------
MEMORY: dict[str, dict[str, str]] = {
    "mr": {
        "memory_saved": "ठेवलं: {fact}. विसरायचं असेल तर 'हे विसरून जा' म्हणा.",
        "memory_what": "काय लक्षात ठेवू? सांगा.",
        "memory_refused": "हे मला लक्षात ठेवता येणार नाही. आकडे, पत्ते, पैसे, औषधं आणि आजार मी ठेवत नाही.",
        "memory_forgot": "विसरलो: {fact}.",
    },
    "hi": {
        "memory_saved": "रख लिया: {fact}। भुलाना हो तो 'यह भूल जाओ' कहिए।",
        "memory_what": "क्या याद रखूँ? बताइए।",
        "memory_refused": "यह मैं याद नहीं रख सकता। नंबर, पते, पैसे, दवाइयाँ और बीमारियाँ मैं नहीं रखता।",
        "memory_forgot": "भूल गया: {fact}।",
    },
    "en": {
        "memory_saved": "Kept: {fact}. To forget it, say 'forget this'.",
        "memory_what": "What should I remember? Tell me.",
        "memory_refused": "I cannot keep that. I do not keep numbers, addresses, money, medicines or illnesses.",
        "memory_forgot": "Forgotten: {fact}.",
    },
}
for _lang, _lines in MEMORY.items():
    R[_lang].update(_lines)
