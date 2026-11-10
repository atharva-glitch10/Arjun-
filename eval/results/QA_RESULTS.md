# QA eval (2026-11-09 20:45) - 75 questions, budgets=relaxed

**Accuracy 67%** (50/75) | **routing 85%** (51/60) | latency p50 3968 ms, p95 12953 ms, mean 5460 ms
wrong/unsafe (answered, but not the expected fact): 10

| category | n | accuracy |
|---|---|---|
| science | 5 | 100% |
| history | 4 | 100% |
| religion | 4 | 75% |
| recipe | 2 | 0% |
| maths | 3 | 33% |
| language | 2 | 100% |
| geography | 4 | 100% |
| health | 4 | 100% |
| sports | 5 | 80% |
| films | 4 | 100% |
| roles | 5 | 40% |
| prices | 3 | 33% |
| news | 3 | 100% |
| weather | 3 | 67% |
| ambiguous | 3 | 100% |
| computed-age | 2 | 0% |
| stt-noisy | 4 | 75% |
| multilingual | 5 | 40% |
| follow-up | 10 | 30% |

| route | n | p50 ms | p95 ms |
|---|---|---|---|
| know | 46 | 1873 | 9282 |
| search | 21 | 11364 | 14568 |
| tool | 2 | 3505 | 5893 |
| refuse_safe | 3 | 4868 | 6299 |

## The 15 worst (question -> query -> top result -> reply -> cause)

- **fu2b** त्या कोणत्या राज्याच्या आहेत
  - queries: None
  - top: None
  - reply: आजीबाई, द्रौपदी मुर्मू या ओदिशा राज्याच्या आहेत.
  - cause: routing (expected search, got know)
- **fu3b** त्यांचा जन्म कधी झाला
  - queries: None
  - top: None
  - reply: आजीबाई, द्रौपदी मुर्मू यांचा जन्म २० जून १९५८ रोजी झाला.
  - cause: wrong_or_missing_fact
- **mat1** बारा गुणिले पंधरा किती होतात
  - queries: None
  - top: None
  - reply: 
  - cause: llm_unavailable_rules_replied
- **mat3** शंभर मधून सदोतीस वजा केले तर किती राहतात
  - queries: None
  - top: None
  - reply: Aajiबाई, शंभर मधून सदोतीस वजा केले तर त्रेसष्ट राहतात.
  - cause: wrong_or_missing_fact
- **mul3** who wrote the Ramayana
  - queries: None
  - top: None
  - reply: Aajiबाई, रामायण महर्षी वाल्मिकींनी लिहिलं आहे.
  - cause: wrong_or_missing_fact
- **mul5** what is the capital of Japan
  - queries: None
  - top: None
  - reply: Aajiबाई, जपानची राजधानी टोकियो आहे.
  - cause: wrong_or_missing_fact
- **pol5** अमेरिकेचे राष्ट्राध्यक्ष कोण आहेत
  - queries: None
  - top: None
  - reply: Aajiबाई, अमेरिकेचे राष्ट्राध्यक्ष जो बायडन आहेत.
  - cause: routing (expected search, got know)
- **rec1** पुरणपोळी कशी करतात
  - queries: None
  - top: None
  - reply: 
  - cause: llm_unavailable_rules_replied
- **rec2** चहा कसा करायचा
  - queries: None
  - top: None
  - reply: 
  - cause: llm_unavailable_rules_replied
- **rel4** एकादशी म्हणजे काय
  - queries: None
  - top: None
  - reply: 
  - cause: llm_unavailable_rules_replied
- **age1** विराट कोहली किती वर्षांचा आहे
  - queries: ['Virat Kohli age today 9 November 2026', 'विराट कोहली किती वर्षांचा आहे']
  - top: None
  - reply: आत्ता माहिती मिळाली नाही.
  - cause: no_results
- **age2** नरेंद्र मोदी यांचं वय किती
  - queries: ['Narendra Modi age today 9 November 2026', 'Narendra Modi नरेंद्र मोदी यांचं वय किती']
  - top: None
  - reply: आत्ता माहिती मिळाली नाही.
  - cause: no_results
- **fu1b** आणि त्यांचं वय किती
  - queries: ['what is the age of Narendra Modi today 9 November 2026', 'Narendra Modi आणि त्यांचं वय किती']
  - top: None
  - reply: आत्ता माहिती मिळाली नाही.
  - cause: no_results
- **fu2a** भारताचे राष्ट्रपती कोण आहेत
  - queries: ['who is the president of India today 9 November 2026', 'Droupadi Murmu भारताचे राष्ट्रपती कोण आहेत']
  - top: None
  - reply: आत्ता माहिती मिळाली नाही.
  - cause: no_results
- **fu4b** आणि त्याची पत्नी कोण
  - queries: ['Virat Kohli wife', 'विराट कोहली पत्नी आणि त्याची पत्नी कोण']
  - top: None
  - reply: आत्ता माहिती मिळाली नाही.
  - cause: no_results