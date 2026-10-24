"""Create a short-lived LiveKit join token for manual testing (e.g. the Agents Playground).

The token EXPLICITLY dispatches the Arjun agent (agent_name from ARJUN_AGENT_NAME, default "arjun")
into the room. Dispatch only happens when the room is CREATED, so by default every run uses a fresh
room name (arjun-test-HHMMSS). Reads LIVEKIT_* from the root .env. The token is copied to the
Windows clipboard and NOT printed; pass --print to show it.

Usage: python scripts/make_token.py [room] [identity] [--print]
"""

import subprocess
import sys
from datetime import datetime, timedelta

from dotenv import dotenv_values
from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants

args = [a for a in sys.argv[1:] if not a.startswith("--")]
room = args[0] if len(args) > 0 else f"arjun-test-{datetime.now():%H%M%S}"
identity = args[1] if len(args) > 1 else "aaji-test"

env = dotenv_values(".env")
key, secret, url = env.get("LIVEKIT_API_KEY"), env.get("LIVEKIT_API_SECRET"), env.get("LIVEKIT_URL")
agent_name = env.get("ARJUN_AGENT_NAME") or "arjun"
if not (key and secret and url):
    raise SystemExit("LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET missing in .env")

token = (
    AccessToken(key, secret)
    .with_identity(identity)
    .with_ttl(timedelta(hours=1))
    .with_grants(VideoGrants(room_join=True, room=room))
    .with_room_config(RoomConfiguration(agents=[RoomAgentDispatch(agent_name=agent_name)]))
    .to_jwt()
)
print(f"url:      {url}\nroom:     {room}\nidentity: {identity}\nagent:    {agent_name}\nvalid:    1 hour")
if "--print" in sys.argv:
    print(token)
else:
    subprocess.run(["clip"], input=token.encode("ascii"), check=True)
    print("token copied to clipboard (not printed)")
