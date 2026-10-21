"""Create a short-lived LiveKit join token for manual testing (e.g. the Agents Playground).

Reads LIVEKIT_API_KEY / LIVEKIT_API_SECRET from the root .env. The token is copied to the Windows
clipboard and NOT printed; pass --print to show it. Usage: python scripts/make_token.py [room] [identity]
"""

import subprocess
import sys
from datetime import timedelta

from dotenv import dotenv_values
from livekit.api import AccessToken, VideoGrants

room = next((a for a in sys.argv[1:] if not a.startswith("--")), "arjun-test")
identity = ([a for a in sys.argv[1:] if not a.startswith("--")] + ["", "aaji-test"])[1] or "aaji-test"

env = dotenv_values(".env")
key, secret, url = env.get("LIVEKIT_API_KEY"), env.get("LIVEKIT_API_SECRET"), env.get("LIVEKIT_URL")
if not (key and secret and url):
    raise SystemExit("LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET missing in .env")

token = (
    AccessToken(key, secret)
    .with_identity(identity)
    .with_ttl(timedelta(hours=1))
    .with_grants(VideoGrants(room_join=True, room=room))
    .to_jwt()
)
print(f"url:      {url}\nroom:     {room}\nidentity: {identity}\nvalid:    1 hour")
if "--print" in sys.argv:
    print(token)
else:
    subprocess.run(["clip"], input=token.encode("ascii"), check=True)
    print("token copied to clipboard (not printed)")
