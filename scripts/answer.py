#!/usr/bin/env python3
"""Turns an 'Answer the call' issue into one soul file + README refresh."""
import datetime, html, json, os, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOULS = ROOT / "souls"
README = ROOT / "README.md"

body = os.environ["ISSUE_BODY"]
user = os.environ["ISSUE_USER"]
repo = os.environ["REPO"]
comment_file = os.environ.get("COMMENT_FILE", "/tmp/comment.md")
gh_out = os.environ.get("GITHUB_OUTPUT")

MAX_TEXT = 40
MILESTONES = {10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000}


def output(**kv):
    if gh_out:
        with open(gh_out, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def finish(status, text, **kv):
    pathlib.Path(comment_file).write_text(text, encoding="utf-8")
    output(status=status, **kv)
    raise SystemExit(0)


def parse(body):
    d = {}
    for part in re.split(r"^### +", body, flags=re.M)[1:]:
        head, _, val = part.partition("\n")
        val = val.strip()
        d[head.strip()] = "" if val == "_No response_" else val
    return d


def load():
    souls = {}
    for f in SOULS.rglob("*.json"):
        s = json.loads(f.read_text("utf-8"))
        souls[s["id"]] = s
    return souls


def descendants(souls, root):
    kids = {}
    for s in souls.values():
        kids.setdefault(s["parent"], []).append(s["id"])
    seen, stack = 0, list(kids.get(root, []))
    while stack:
        n = stack.pop()
        seen += 1
        stack.extend(kids.get(n, []))
    return seen


def md(s):
    return html.escape(s).replace("|", "\\|").replace("`", "'")


fields = parse(body)
souls = load()
latest = max(souls) if souls else -1

# ---- validate -------------------------------------------------------------
if user.endswith("[bot]"):
    finish("rejected", "The call is for souls, not bots. (Agents: ask your human.)")

text = " ".join(fields.get("Your soul", "").split())
glyph = fields.get("Glyph", "").strip() or "✦"
parent_raw = fields.get("Answering soul #", "").strip().lstrip("#")

if not text or len(text) > MAX_TEXT:
    finish("rejected", f"Your soul must be 1-{MAX_TEXT} characters. Open a new call and try again.")
if re.search(r"https?:|www\.|\.(com|io|ru|xyz|ly)\b", text, re.I):
    finish("rejected", "No links in souls. Souls are words, not ads.")
block = (ROOT / "blocklist.txt")
if block.exists():
    words = [w.strip().lower() for w in block.read_text().splitlines() if w.strip() and not w.startswith("#")]
    if any(w in text.lower() for w in words):
        finish("rejected", "That soul isn't allowed here. Try another.")
if len(glyph) > 8:
    glyph = glyph[:8]

parent = int(parent_raw) if parent_raw.isdigit() else latest
if parent not in souls:
    parent = latest

today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
if user != repo.split("/")[0] and any(
    s["author"] == user and s["created"].startswith(today) for s in souls.values()
):
    finish("rejected", "You already answered today. Come back tomorrow. The call will still be here.")

# ---- create ---------------------------------------------------------------
sid = latest + 1
soul = {
    "id": sid,
    "parent": parent,
    "author": user,
    "text": text,
    "glyph": glyph,
    "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
}
path = SOULS / f"{sid // 1000:03d}" / f"{sid:06d}.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(soul, ensure_ascii=False) + "\n", encoding="utf-8")
souls[sid] = soul

# ---- README refresh -------------------------------------------------------
total = len(souls)
recent = sorted(souls.values(), key=lambda s: -s["id"])[:10]
rows = "\n".join(
    f"| #{s['id']} | {md(s['glyph'])} | {md(s['text'])} | @{s['author']} |" for s in recent
)
answer_url = f"https://github.com/{repo}/issues/new?template=answer-the-call.yml&parent={sid}"
newest = f"**#{sid}** {md(glyph)} &nbsp; *{md(text)}* &nbsp; by @{user}"

r = README.read_text("utf-8")
def swap(tag, new):
    global r
    r = re.sub(rf"<!--{tag}-->.*?<!--/{tag}-->", f"<!--{tag}-->{new}<!--/{tag}-->", r, flags=re.S)
swap("COUNT", f"{total:,}")
swap("NEWEST", newest)
swap("LINK", answer_url)
swap("RECENT", "\n| # | | soul | by |\n|---|---|---|---|\n" + rows + "\n")
README.write_text(r, encoding="utf-8")

# ---- reply ----------------------------------------------------------------
lines = [f"## 🖤 You are soul **#{sid}**", "", f"{glyph} *{text}*", "",
         "Your soul is now a real commit in this repo, under your name."]
if sid <= 100:
    lines += ["", "🏅 **Founding Soul**: one of the first 100 to answer."]
if sid in MILESTONES or sid % 1000 == 0:
    lines += ["", f"🎉 **Milestone:** {sid:,} souls have answered the call."]
p = souls.get(parent)
if p and p["author"] not in (user, "the-call"):
    n = descendants(souls, parent)
    lines += ["", f"@{p['author']}, your soul #{parent} was answered by @{user}. It now has {n} descendant(s)."]
lines += ["", f"**Next:** [answer soul #{sid} yourself]({answer_url}) in someone else's voice, or ⭐ star the repo to light a star in the sky."]
finish("ok", "\n".join(lines), id=sid)
