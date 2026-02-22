import asyncio
import json
import re
import random
import signal
import sys
from datetime import datetime, timezone
from typing import Optional, Dict

import aiohttp
import discord
from discord import app_commands

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN      = "MTQwOTI1ODg3MzUzMzIzNTI4Mw.GVk9CI.iiYKGxTkqCTjbK5vusRtKEtjRgc2nrZvChnot8"
CHECK_EVERY        = 60       # seconds between each check
MAX_RETRIES        = 5        # max consecutive errors before session reset
RETRY_BASE_DELAY   = 2.0      # exponential backoff base in seconds
SESSION_TIMEOUT    = aiohttp.ClientTimeout(total=30, connect=10)

# ─── USER AGENTS ──────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# ─── BANNED PAGE KEYWORDS ─────────────────────────────────────────────────────
BANNED_KEYWORDS = [
    "page isn't available", "sorry, this page isn't available",
    "page not found", "content isn't available",
    "user has been banned", "account has been disabled",
    "couldn't find this account", "this page doesn't exist",
    "the link you followed may be broken", "user not found",
    "has been banned", "has been disabled", "suspended",
    "this account has been banned", "this account has been disabled",
    "instagram account has been deleted", "no longer exists",
    "the user you requested could not be found",
    "hmm... this page doesn't exist",
]

# ─── BOT SETUP ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
bot = discord.Client(
    intents=intents,
    heartbeat_timeout=60,
    assume_unsync_clock=True,
)
tree = app_commands.CommandTree(bot)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def parse_number(text: str) -> Optional[int]:
    """Convert '95.3k', '1M', '2.5B' etc to integer."""
    t = text.lower().replace(",", "").strip()
    mult = 1
    if t.endswith("k"):
        mult, t = 1_000, t[:-1]
    elif t.endswith("m"):
        mult, t = 1_000_000, t[:-1]
    elif t.endswith("b"):
        mult, t = 1_000_000_000, t[:-1]
    try:
        return int(float(t) * mult)
    except ValueError:
        return None


def get_headers(extra: dict = None) -> dict:
    """Return randomized browser-like headers."""
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if extra:
        h.update(extra)
    return h


def format_count(n: Optional[int]) -> str:
    """Format like Instagram: 95300 -> 95.3K, 1000000 -> 1M"""
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


# ─── SESSION MANAGER ──────────────────────────────────────────────────────────

_session: Optional[aiohttp.ClientSession] = None


async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(
            limit=20,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            force_close=False,
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=SESSION_TIMEOUT,
        )
    return _session


async def safe_close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


# ─── FETCH WITH RETRY ─────────────────────────────────────────────────────────

async def _fetch_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict,
    as_json: bool = False,
    retries: int = 3,
):
    """Fetch URL with exponential backoff. Returns (status, content) or (None, None)."""
    for attempt in range(retries):
        try:
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if as_json:
                    try:
                        data = await resp.json(content_type=None)
                        return resp.status, data
                    except Exception:
                        return resp.status, None
                else:
                    text = await resp.text(errors="replace")
                    return resp.status, text
        except (
            aiohttp.ClientConnectorError,
            asyncio.TimeoutError,
            aiohttp.ServerDisconnectedError,
        ) as e:
            delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
            print(f"  [retry {attempt+1}/{retries}] {url[:55]}... {type(e).__name__}, wait {delay:.1f}s")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
        except Exception as e:
            print(f"  [fetch error] {url[:55]}... {e}")
            break
    return None, None


# ─── INSTAGRAM PROFILE DATA ───────────────────────────────────────────────────

class IGProfile:
    """Holds all fetched Instagram profile data."""
    def __init__(self):
        self.username:    Optional[str] = None
        self.full_name:   Optional[str] = None
        self.bio:         Optional[str] = None
        self.followers:   Optional[int] = None
        self.following:   Optional[int] = None
        self.posts:       Optional[int] = None
        self.pic_url:     Optional[str] = None
        self.is_verified: bool = False
        self.is_private:  bool = False
        self.is_active:   bool = False


async def fetch_profile(session: aiohttp.ClientSession, username: str) -> IGProfile:
    """
    Fetch full Instagram profile using 3 methods.
    Returns IGProfile — check .is_active to see if recovered.
    """
    profile = IGProfile()

    # ── Method 1: Official API ─────────────────────────────────────────────────
    api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = get_headers({
        "X-IG-App-ID": "936619743392459",
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/{username}/",
    })
    status, data = await _fetch_with_retry(session, api_url, headers, as_json=True)
    if status == 200 and isinstance(data, dict):
        user = (data.get("data") or {}).get("user")
        if user and data.get("status") == "ok":
            profile.is_active   = True
            profile.username    = user.get("username")
            profile.full_name   = user.get("full_name")
            profile.bio         = user.get("biography")
            profile.pic_url     = user.get("profile_pic_url_hd") or user.get("profile_pic_url")
            profile.is_verified = user.get("is_verified", False)
            profile.is_private  = user.get("is_private", False)
            profile.followers   = (user.get("edge_followed_by") or {}).get("count") or user.get("follower_count")
            profile.following   = (user.get("edge_follow") or {}).get("count") or user.get("following_count")
            profile.posts       = (user.get("edge_owner_to_timeline_media") or {}).get("count") or user.get("media_count")
            return profile
    if status == 404:
        return profile

    # ── Method 2: Legacy JSON ──────────────────────────────────────────────────
    json_url = f"https://www.instagram.com/{username}/?__a=1&__d=dis"
    status, data = await _fetch_with_retry(session, json_url, get_headers(), as_json=True)
    if status == 200 and isinstance(data, dict):
        user = (data.get("graphql") or {}).get("user")
        if user and user.get("username"):
            profile.is_active   = True
            profile.username    = user.get("username")
            profile.full_name   = user.get("full_name")
            profile.bio         = user.get("biography")
            profile.pic_url     = user.get("profile_pic_url_hd") or user.get("profile_pic_url")
            profile.is_verified = user.get("is_verified", False)
            profile.is_private  = user.get("is_private", False)
            profile.followers   = (user.get("edge_followed_by") or {}).get("count")
            profile.following   = (user.get("edge_follow") or {}).get("count")
            profile.posts       = (user.get("edge_owner_to_timeline_media") or {}).get("count")
            return profile
    if status == 404:
        return profile

    # ── Method 3: HTML Scraping ────────────────────────────────────────────────
    html_url = f"https://www.instagram.com/{username}/"
    status, html = await _fetch_with_retry(session, html_url, get_headers(), as_json=False)
    if html is None:
        print(f"  [{username}] All 3 methods failed — no response")
        return profile
    if status == 404:
        return profile

    html_lower = html.lower()

    # Check for banned/deleted page keywords
    for kw in BANNED_KEYWORDS:
        if kw in html_lower:
            print(f"  [{username}] Banned keyword: '{kw}'")
            return profile

    # Try shared data JSON in script tags
    for pattern in [
        r'<script type="text/javascript">window\._sharedData\s*=\s*(.*?);</script>',
        r'window\.__additionalDataLoaded\("ProfilePage",(.*?)\);',
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                d = json.loads(m.group(1))
                pages = d.get("entry_data", {}).get("ProfilePage", [])
                if pages:
                    u = pages[0].get("graphql", {}).get("user", {})
                    if u.get("username"):
                        profile.is_active   = True
                        profile.username    = u.get("username")
                        profile.full_name   = u.get("full_name")
                        profile.bio         = u.get("biography")
                        profile.pic_url     = u.get("profile_pic_url_hd") or u.get("profile_pic_url")
                        profile.is_verified = u.get("is_verified", False)
                        profile.is_private  = u.get("is_private", False)
                        profile.followers   = (u.get("edge_followed_by") or {}).get("count")
                        profile.following   = (u.get("edge_follow") or {}).get("count")
                        profile.posts       = (u.get("edge_owner_to_timeline_media") or {}).get("count")
                        return profile
            except Exception:
                pass

    # Regex fallback for follower count in raw HTML
    for pat in [
        r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)',
        r'"follower_count"\s*:\s*(\d+)',
        r'"followers"\s*:\s*(\d+)',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            profile.is_active = True
            profile.followers = int(m.group(1))
            profile.username  = username
            return profile

    # Meta description fallback
    m = re.search(r'property="og:description"\s+content="([^"]+)"', html)
    if m:
        content = m.group(1)
        fm = re.search(r'([\d,.]+[kKmMbB]?)\s+Followers?', content, re.IGNORECASE)
        if fm:
            followers = parse_number(fm.group(1))
            if followers:
                profile.is_active = True
                profile.followers = followers
                profile.username  = username
                return profile

    # No follower word at all = banned
    if "follower" not in html_lower:
        return profile

    return profile


# ─── BUILD EMBED HELPER ───────────────────────────────────────────────────────

def build_profile_embed(ig: IGProfile, username: str) -> discord.Embed:
    """Build an Instagram-style Discord embed card from IGProfile data."""
    profile_url    = f"https://www.instagram.com/{username}/"
    verified_badge = " ✔️" if ig.is_verified else ""
    private_tag    = " 🔒" if ig.is_private  else ""
    display_name   = ig.full_name or ig.username or username

    embed = discord.Embed(color=0x00C853, url=profile_url)
    embed.set_author(
        name=f"{display_name}{verified_badge}{private_tag}",
        url=profile_url,

    )

    # Stats row: posts · followers · following
    stats = (
        f"**{format_count(ig.posts)}** posts   "
        f"**{format_count(ig.followers)}** followers   "
        f"**{format_count(ig.following)}** following"
    )
    embed.add_field(name="\u200b", value=stats, inline=False)

    if ig.bio:
        embed.add_field(name="\u200b", value=ig.bio, inline=False)

    if ig.pic_url:
        embed.set_thumbnail(url=ig.pic_url)

    embed.set_footer(
        text="instagram.com",
        icon_url="https://www.instagram.com/favicon.ico",
    )
    return embed


# ─── MONITOR CLASS ────────────────────────────────────────────────────────────

class IGMonitor:
    def __init__(self, username: str, channel_id: int, requester_id: int):
        self.username           = username.lower().lstrip("@")
        self.channel_id         = channel_id
        self.requester_id       = requester_id
        self.started            = datetime.now(timezone.utc)
        self._done              = asyncio.Event()
        self.task: Optional[asyncio.Task] = None
        self.notified           = False
        self.check_count        = 0
        self.consecutive_errors = 0

    def format_time(self, total_seconds: int) -> str:
        h, rem = divmod(total_seconds, 3600)
        m, s   = divmod(rem, 60)
        return (
            f"{h} {'hour' if h == 1 else 'hours'}, "
            f"{m} {'minute' if m == 1 else 'minutes'}, "
            f"{s} {'second' if s == 1 else 'seconds'}"
        )

    async def _notify(self, ig: IGProfile):
        """Send recovery notification: plain text header + Instagram-style embed."""
        if self.notified:
            return

        channel = None
        for attempt in range(5):
            try:
                channel = bot.get_channel(self.channel_id) or await bot.fetch_channel(self.channel_id)
                break
            except Exception:
                await asyncio.sleep(2 ** attempt)
        if not channel:
            print(f"[ERROR] Could not get channel for @{self.username}")
            return

        total_secs  = int((datetime.now(timezone.utc) - self.started).total_seconds())
        fol_text    = f"{ig.followers:,}" if ig.followers else "N/A"
        time_text   = self.format_time(total_secs)

        profile_url = f"https://www.instagram.com/{self.username}/"
        msg = (
            f"[Account Recovered | @{self.username}]({profile_url}) "
            f"🏆✅ | Followers : {fol_text} | ⏱️ Time taken : {time_text}"
        )

        for attempt in range(5):
            try:
                await channel.send(content=msg)
                print(f"[OK] Recovery sent for @{self.username}")
                self.notified = True
                break
            except (discord.HTTPException, discord.ConnectionClosed) as e:
                print(f"[WARN] Send attempt {attempt+1} failed: {e}")
                await asyncio.sleep(3 * (attempt + 1))

        self._done.set()

    async def start(self, session: aiohttp.ClientSession):
        print(f"[START] Monitoring @{self.username}")
        while not self._done.is_set():
            self.check_count += 1
            try:
                ig = await fetch_profile(session, self.username)
                if ig.is_active:
                    print(f"[RECOVERED] @{self.username} (check #{self.check_count})")
                    await self._notify(ig)
                    return
                else:
                    self.consecutive_errors = 0
                    print(f"[BANNED] @{self.username} still down (check #{self.check_count})")
            except asyncio.CancelledError:
                print(f"[CANCELLED] @{self.username}")
                return
            except Exception as e:
                self.consecutive_errors += 1
                print(f"[ERROR] @{self.username} #{self.consecutive_errors}: {e}")
                if self.consecutive_errors >= MAX_RETRIES:
                    print(f"[RESET] Recreating session after {MAX_RETRIES} errors...")
                    await safe_close_session()
                    session = await get_session()
                    self.consecutive_errors = 0

            jitter = random.uniform(0, 10)
            await asyncio.sleep(CHECK_EVERY + jitter)

    def cancel(self):
        self._done.set()
        if self.task and not self.task.done():
            self.task.cancel()
        print(f"[STOP] Monitor cancelled for @{self.username}")


# ─── GLOBAL STATE ─────────────────────────────────────────────────────────────

active_monitors: Dict[str, IGMonitor] = {}


# ─── BOT EVENTS ───────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"[BOT] Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await tree.sync()
        print(f"[BOT] Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"[BOT] Sync error: {e}")


@bot.event
async def on_disconnect():
    print("[BOT] Disconnected — discord.py will auto-reconnect.")


@bot.event
async def on_resumed():
    print("[BOT] Reconnected & session resumed.")


@bot.event
async def on_error(event, *args, **kwargs):
    print(f"[BOT] Unhandled error in '{event}':", sys.exc_info())


# ─── SLASH COMMANDS ───────────────────────────────────────────────────────────

@tree.command(name="unban", description="Monitor a banned Instagram account for recovery")
@app_commands.describe(username="Instagram username (without @)")
async def unban_cmd(inter: discord.Interaction, username: str):
    clean = username.lower().lstrip("@")

    if clean in active_monitors and not active_monitors[clean]._done.is_set():
        await inter.response.send_message(
            f"Already monitoring **@{clean}**. Use `/cancel {clean}` to stop.",
            ephemeral=True,
        )
        return

    await inter.response.defer(ephemeral=True)
    try:
        session = await get_session()
        ig = await fetch_profile(session, clean)

        if ig.is_active:
            fol_text = f"{ig.followers:,}" if ig.followers else "N/A"
            profile_url = f"https://www.instagram.com/{clean}/"
            msg = (
                f"[Account Recovered | @{clean}]({profile_url}) "
                f"🏆✅ | Followers : {fol_text} | ⏱️ Time taken : 0 hours, 0 minutes, 0 seconds"
            )
            await inter.followup.send(content=msg)
            return

        monitor = IGMonitor(clean, inter.channel_id, inter.user.id)
        active_monitors[clean] = monitor
        monitor.task = asyncio.create_task(monitor.start(session))

        def _cleanup(task: asyncio.Task):
            if clean in active_monitors and active_monitors[clean] is monitor:
                del active_monitors[clean]
            try:
                exc = task.exception()
                if exc:
                    print(f"[ERROR] Task for @{clean}: {exc}")
            except asyncio.CancelledError:
                pass

        monitor.task.add_done_callback(_cleanup)
        await inter.followup.send(
            f"Now monitoring **@{clean}**. Will notify here when recovered!",
            ephemeral=True,
        )
    except Exception as e:
        await inter.followup.send(f"Error: {e}", ephemeral=True)


@tree.command(name="cancel", description="Stop monitoring an account (blank = stop all)")
@app_commands.describe(username="Username to stop (leave blank to stop all)")
async def cancel_cmd(inter: discord.Interaction, username: Optional[str] = None):
    if not active_monitors:
        await inter.response.send_message("No active monitors.", ephemeral=True)
        return

    if username:
        clean = username.lower().lstrip("@")
        mon = active_monitors.get(clean)
        if mon and not mon._done.is_set():
            mon.cancel()
            active_monitors.pop(clean, None)
            await inter.response.send_message(f"Stopped monitoring **@{clean}**.", ephemeral=True)
        else:
            await inter.response.send_message(f"Not monitoring **@{clean}**.", ephemeral=True)
    else:
        count = sum(1 for m in active_monitors.values() if not m._done.is_set())
        for mon in list(active_monitors.values()):
            mon.cancel()
        active_monitors.clear()
        await inter.response.send_message(f"Stopped all {count} monitor(s).", ephemeral=True)


@tree.command(name="status", description="Show all active monitors with elapsed time")
async def status_cmd(inter: discord.Interaction):
    running = {n: m for n, m in active_monitors.items() if not m._done.is_set()}
    if not running:
        await inter.response.send_message("No monitors currently running.", ephemeral=True)
        return
    lines = []
    for name, mon in running.items():
        d = datetime.now(timezone.utc) - mon.started
        h, rem = divmod(int(d.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        lines.append(f"• **@{name}** — {h}h {m}m {s}s | checks: {mon.check_count}")
    await inter.response.send_message(
        "**Active Monitors:**\n" + "\n".join(lines), ephemeral=True
    )


@tree.command(name="list", description="List all accounts being monitored")
async def list_cmd(inter: discord.Interaction):
    running = [f"• @{n}" for n, m in active_monitors.items() if not m._done.is_set()]
    if not running:
        await inter.response.send_message("No monitors running.", ephemeral=True)
        return
    await inter.response.send_message("**Monitoring:**\n" + "\n".join(running), ephemeral=True)


@tree.command(name="check", description="Instantly check if an Instagram account is active or banned")
@app_commands.describe(username="Instagram username to check")
async def check_cmd(inter: discord.Interaction, username: str):
    clean = username.lower().lstrip("@")
    await inter.response.defer(ephemeral=True)
    try:
        session = await get_session()
        ig = await fetch_profile(session, clean)
        if ig.is_active:
            fol = f"{ig.followers:,}" if ig.followers else "N/A"
            await inter.followup.send(
                f"**@{clean}** is **ACTIVE** | Followers: {fol}", ephemeral=True
            )
        else:
            await inter.followup.send(
                f"**@{clean}** appears **banned / inactive**.", ephemeral=True
            )
    except Exception as e:
        await inter.followup.send(f"Error: {e}", ephemeral=True)


# ─── GRACEFUL SHUTDOWN ────────────────────────────────────────────────────────

async def shutdown():
    print("[BOT] Shutting down gracefully...")
    for mon in list(active_monitors.values()):
        mon.cancel()
    await safe_close_session()
    await bot.close()


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig, lambda: asyncio.ensure_future(shutdown(), loop=loop)
            )
        except NotImplementedError:
            pass  # Windows

    try:
        loop.run_until_complete(bot.start(DISCORD_TOKEN, reconnect=True))
    except KeyboardInterrupt:
        loop.run_until_complete(shutdown())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
