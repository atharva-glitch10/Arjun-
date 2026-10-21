from dotenv import dotenv_values

v = dotenv_values(".env")
for k in ["GNANI_API_KEY", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]:
    val = v.get(k)
    status = f"SET ({len(val)} chars)" if val else "MISSING"
    print(f"{k:22} {status}")
