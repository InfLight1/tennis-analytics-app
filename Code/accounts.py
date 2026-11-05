"""
accounts.py -- sign-in, teams and who may see which report.

Built for school teams of minors: no email addresses are collected. A coach
creates a team (needs the app passcode, so not anyone can be a coach) and
gets a short team code; players join with that code, a username and a
password. A coach can reset a player's password, so no reset emails needed.
Solo players (no team; also need the passcode for now) may add an optional
email for password resets; it is never shown to a page or a coach.

Storage is any dict-like object with get/put semantics (`store[key]`,
`store.get(key)`, `key in store`, `del store[key]`). On Modal it's a
modal.Dict; in tests a plain dict. Keys:
  user:<username>     {id, username, name, role, team_id, salt, pw, created, email?}
  team:<team_id>      {id, name, code, coaches: [username], players: [username]}
  teamcode:<CODE>     team_id
  session:<token>     {username, expires}
  jobs:<username>     [{job_id, slot, date}]   reports this player has claimed
  owner:<job_id>      username who started the upload
  push:<username>     [token]   phones that get "your report is ready" alerts
Passwords: PBKDF2-SHA256, 200k rounds, random salt.
"""

import hashlib
import hmac
import re
import secrets
import time

SESSION_DAYS = 60
PW_ROUNDS = 200_000
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I
USERNAME_RE = re.compile(r"[a-z0-9_.-]{3,24}")
SLOTS = ("player_1", "player_2", "player_3", "player_4")   # 3/4 for doubles


class AccountError(Exception):
    """A problem to show the person as is (plain words)."""


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PW_ROUNDS).hex()


def _clean_username(u):
    u = (u or "").strip().lower()
    if not USERNAME_RE.fullmatch(u):
        raise AccountError("Usernames are 3-24 letters, numbers, dots, dashes or underscores.")
    return u


def _check_password(pw):
    if len(pw or "") < 8:
        raise AccountError("Passwords need at least 8 characters.")


class Accounts:
    def __init__(self, store, now=time.time):
        self.s = store
        self.now = now

    # ── users and teams ──────────────────────────────────────────────────
    def _new_user(self, username, password, name, role, team_id):
        username = _clean_username(username)
        _check_password(password)
        if f"user:{username}" in self.s:
            raise AccountError("That username is taken.")
        salt = secrets.token_hex(16)
        user = {"id": username, "username": username, "name": (name or username).strip()[:40],
                "role": role, "team_id": team_id, "salt": salt, "pw": _hash(password, salt),
                "created": self.now()}
        self.s[f"user:{username}"] = user
        return user

    def _new_code(self):
        for _ in range(50):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if f"teamcode:{code}" not in self.s:
                return code
        raise AccountError("Couldn't make a team code. Try again.")

    def create_team(self, team_name, username, password, name):
        """A coach signs up and creates their team. (Caller checks the passcode.)"""
        team_id = secrets.token_hex(6)
        code = self._new_code()
        user = self._new_user(username, password, name, "coach", team_id)
        self.s[f"team:{team_id}"] = {"id": team_id, "name": (team_name or "My team").strip()[:60],
                                     "code": code, "coaches": [user["username"]], "players": []}
        self.s[f"teamcode:{code}"] = team_id
        return user, self.s[f"team:{team_id}"]

    def join_team(self, code, username, password, name):
        """A player signs up with their team's code."""
        team_id = self.s.get(f"teamcode:{(code or '').strip().upper()}")
        if not team_id:
            raise AccountError("That team code doesn't match a team. Check it with your coach.")
        user = self._new_user(username, password, name, "player", team_id)
        team = self.s[f"team:{team_id}"]
        team["players"] = team["players"] + [user["username"]]
        self.s[f"team:{team_id}"] = team
        return user

    def solo_signup(self, username, password, name, email=""):
        """A player with no team. (Caller checks the passcode.)"""
        email = (email or "").strip().lower()[:120]
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise AccountError("That email doesn't look right. You can leave it empty.")
        user = self._new_user(username, password, name, "player", None)
        if email:
            user["email"] = email
            self.s[f"user:{user['username']}"] = user
        return user

    def add_to_team(self, username, code):
        """A solo player joins a team later; their matches come with them."""
        user = self.user(username)
        if not user or user["role"] != "player" or user.get("team_id"):
            raise AccountError("You're already on a team.")
        team_id = self.s.get(f"teamcode:{(code or '').strip().upper()}")
        if not team_id:
            raise AccountError("That team code doesn't match a team. Check it with your coach.")
        user["team_id"] = team_id
        self.s[f"user:{user['username']}"] = user
        team = self.s[f"team:{team_id}"]
        team["players"] = team["players"] + [user["username"]]
        self.s[f"team:{team_id}"] = team
        return user

    def team(self, team_id):
        return self.s.get(f"team:{team_id}")

    def user(self, username):
        return self.s.get(f"user:{(username or '').strip().lower()}")

    def reset_password(self, coach, player_username, new_password):
        """A coach sets a new password for a player on their own team."""
        p = self.user(player_username)
        if not p or coach["role"] != "coach" or p["team_id"] != coach["team_id"]:
            raise AccountError("That player isn't on your team.")
        _check_password(new_password)
        p["salt"] = secrets.token_hex(16)
        p["pw"] = _hash(new_password, p["salt"])
        self.s[f"user:{p['username']}"] = p

    # ── sessions ─────────────────────────────────────────────────────────
    def sign_in(self, username, password):
        u = self.user(username)
        # same work and same message whether or not the user exists
        given = _hash(password or "", u["salt"] if u else "00" * 16)
        if not u or not hmac.compare_digest(given, u["pw"]):
            raise AccountError("Wrong username or password.")
        return self.new_session(u["username"])

    def new_session(self, username):
        token = secrets.token_urlsafe(32)
        self.s[f"session:{token}"] = {"username": username, "expires": self.now() + SESSION_DAYS * 86400}
        return token

    def session_user(self, token):
        if not token:
            return None
        sess = self.s.get(f"session:{token}")
        if not sess:
            return None
        if sess["expires"] < self.now():
            del self.s[f"session:{token}"]
            return None
        return self.user(sess["username"])

    def sign_out(self, token):
        if token and f"session:{token}" in self.s:
            del self.s[f"session:{token}"]

    # ── reports ──────────────────────────────────────────────────────────
    def set_owner(self, job_id, username):
        self.s[f"owner:{job_id}"] = username

    def owner(self, job_id):
        return self.s.get(f"owner:{job_id}")

    def claim(self, username, job_id, slot, date=None):
        """'This is me' on a report: the player is `slot` in that match."""
        if slot not in SLOTS:
            raise AccountError("Unknown player in this report.")
        jobs = [j for j in self.s.get(f"jobs:{username}", []) if j["job_id"] != job_id]
        jobs.append({"job_id": job_id, "slot": slot, "date": date or time.strftime("%Y-%m-%d")})
        self.s[f"jobs:{username}"] = jobs

    def unclaim(self, username, job_id):
        self.s[f"jobs:{username}"] = [j for j in self.s.get(f"jobs:{username}", []) if j["job_id"] != job_id]

    def match_names(self, team_id, names):
        """Which teammates the typed player names are: {slot: username}.
        A name matches a player's full name, username, or first name when
        only one player on the team has that first name. Not case-sensitive."""
        players = [self.user(u) for u in (self.team(team_id) or {}).get("players", [])]
        return self._match_in([p for p in players if p], names)

    @staticmethod
    def _match_in(players, names):
        firsts = {}
        for p in players:
            firsts.setdefault(p["name"].split()[0].lower() if p["name"].split() else "", []).append(p)
        out = {}
        for slot, typed in names.items():
            t = " ".join((typed or "").lower().split())
            if not t:
                continue
            hit = next((p for p in players if t in (p["name"].lower(), p["username"])), None)
            if not hit and len(firsts.get(t, [])) == 1:
                hit = firsts[t][0]
            if hit and hit["username"] not in out.values():
                out[slot] = hit["username"]
        return out

    def auto_claim(self, job_id, names, date=None):
        """Add the report to each named teammate's matches (the uploader's
        team). Re-run after a rename: players no longer named are taken off."""
        owner = self.user(self.owner(job_id))
        if not owner:
            return {}
        if owner.get("team_id"):
            found = self.match_names(owner["team_id"], names)
            people = (self.team(owner["team_id"]) or {}).get("players", [])
        else:   # a solo player: only their own name can match
            found = self._match_in([owner], names)
            people = [owner["username"]]
        for u in people:
            slot = next((s for s, name in found.items() if name == u), None)
            had = next((j for j in self.claims(u) if j["job_id"] == job_id), None)
            if slot:
                self.claim(u, job_id, slot, (had or {}).get("date") or date)
                if had and had.get("result"):
                    self.set_result(u, job_id, had["result"])
            elif had:
                self.unclaim(u, job_id)
        return found

    def set_result(self, username, job_id, result):
        """The player's own Win/Loss for a match (the video often stops before the match ends)."""
        if result not in ("win", "loss", None):
            raise AccountError("Result is win or loss.")
        jobs = self.claims(username)
        for j in jobs:
            if j["job_id"] == job_id:
                j["result"] = result
        self.s[f"jobs:{username}"] = jobs

    def claims(self, username):
        return list(self.s.get(f"jobs:{username}", []))

    def claimed_by(self, job_id, usernames):
        """Which of these users claimed this report (for access checks)."""
        return [u for u in usernames if any(j["job_id"] == job_id for j in self.s.get(f"jobs:{u}", []))]

    def can_see(self, user, job_id):
        """Owner, a player who claimed it, or a coach of either."""
        if not user:
            return False
        owner = self.owner(job_id)
        people = {owner} if owner else set()
        if any(j["job_id"] == job_id for j in self.claims(user["username"])):
            return True
        if owner == user["username"]:
            return True
        if user["role"] == "coach":
            team = self.team(user["team_id"]) or {}
            members = set(team.get("players", []))
            return bool((people & members) or self.claimed_by(job_id, members))
        return False

    # ── alerts ───────────────────────────────────────────────────────────
    def add_push_token(self, username, token):
        token = (token or "").strip()[:200]
        if not token:
            raise AccountError("Missing phone token.")
        self.s[f"push:{username}"] = ([token] + [t for t in self.s.get(f"push:{username}", []) if t != token])[:5]

    def people_on(self, job_id):
        """Who hears about this match: whoever filmed it and the teammates named in it."""
        owner = self.user(self.owner(job_id))
        if not owner:
            return []
        team = self.team(owner.get("team_id")) or {}
        return sorted({owner["username"], *self.claimed_by(job_id, team.get("players", []))})

    def push_tokens(self, usernames):
        return [t for u in usernames for t in self.s.get(f"push:{u}", [])]

    # ── deleting an account ──────────────────────────────────────────────
    def owned_jobs(self, username):
        return [k.split(":", 1)[1] for k in list(self.s.keys())
                if k.startswith("owner:") and self.s.get(k) == username]

    def jobs_lost_with(self, username):
        """Reports that go with this account. A match with a teammate in it stays for them."""
        u = self.user(username)
        team = self.team(u.get("team_id")) or {} if u else {}
        others = [p for p in team.get("players", []) if p != username]
        return [j for j in self.owned_jobs(username) if not self.claimed_by(j, others)]

    def delete_user(self, username):
        """Removes the account for good. Returns the reports to delete with it. Their sessions stop
        working by themselves (a session for a missing user is no one)."""
        u = self.user(username)
        if not u:
            raise AccountError("That account doesn't exist.")
        name = u["username"]
        lost = self.jobs_lost_with(name)
        team = self.team(u.get("team_id"))
        others = [p for p in (team or {}).get("players", []) if p != name]
        for job in self.owned_jobs(name):
            keeper = next(iter(self.claimed_by(job, others)), None)
            if keeper:
                self.s[f"owner:{job}"] = keeper
            else:
                del self.s[f"owner:{job}"]
        if team:
            team["players"] = others
            team["coaches"] = [c for c in team.get("coaches", []) if c != name]
            self.s[f"team:{team['id']}"] = team
        for key in (f"user:{name}", f"jobs:{name}", f"push:{name}"):
            if key in self.s:
                del self.s[key]
        return lost

    def can_change(self, user, job_id):
        """Rename or delete: the person who uploaded it, or their coach."""
        if not user:
            return False
        owner = self.owner(job_id)
        if owner == user["username"]:
            return True
        if user["role"] == "coach" and owner:
            o = self.user(owner)
            return bool(o and o["team_id"] == user["team_id"])
        return False


def public_user(u):
    """What the page may see about a user (never the password hash)."""
    return u and {k: u[k] for k in ("username", "name", "role", "team_id")}
