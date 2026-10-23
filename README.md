# Course Hawk

Finds free courses from providers worldwide, checks them, and sends you a preview in Telegram.
You tap **Approve**, and it posts to your channel in the next time slot.

Sources:

- **Paid courses made free by coupons** (Udemy): found on public coupon sites, and each coupon is
  checked on Udemy to really show a price of 0. Posts whose coupon later ends are marked **EXPIRED**.
- **Microsoft Learn**: new and updated learning paths from its public catalog API.
- **YouTube full courses**: new full-length courses from channels like freeCodeCamp.
- **Curated catalog** (`course_hawk/catalog.json`): hand-picked free courses from Harvard CS50,
  Kaggle, Hugging Face, Google, MIT, Cisco, IBM, AWS, Coursera (audit), NPTEL and more. Two are
  offered a day, and each link is checked before posting. Add your own entries to the file.

Everything runs free on GitHub Actions (public repo) with no server or database: state lives in
`state/state.json`, which each run commits back.

## How a run works

Every 15 minutes the workflow runs `python -m course_hawk`, which:

1. Reads your button taps and messages to the bot.
2. Posts the best queued courses if a post slot is due (08:00, 12:30, 17:30, 20:00, 21:30 IST).
   Right before posting, coupons are price-checked again and free course links are checked.
3. Rechecks coupon posts from the last 5 days every 3 hours and marks ended coupons as expired.
4. At 07:30, 12:00, 17:00 and 21:00 IST, scans the sources and sends previews: up to 6 coupon
   courses and 4 always-free courses.

## Your bot buttons

| Button | What it does |
| --- | --- |
| ✅ Approve | Queue for the next slot (posts at once if under 12 hours left) |
| ⚡ Post now | Price check, then post straight away |
| ⏭ Skip | Drop it; it is not offered again for 30 days |
| 🚫 Ban instructor | Skip and never offer that instructor again |

Reply to a preview with text to replace its description. `/queue` lists approved courses,
`/status` shows counts. Approvals are picked up on the next run, so allow up to 15 minutes.

## Setup

1. **Bot.** Create a new bot with [@BotFather](https://t.me/BotFather) (`/newbot`). Use a separate bot
   from Deal Hawk: two programs reading the same bot's messages steal each other's button taps.
2. **Channel.** Add the bot to your channel as an admin with permission to post and edit messages.
3. **Your chat ID.** Send any message to your new bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy `message.chat.id`.
4. **Secrets.** In GitHub: Settings → Secrets and variables → Actions → New repository secret:
   - `TELEGRAM_BOT_TOKEN`: the token from BotFather
   - `TELEGRAM_CHANNEL`: the channel, for example `@coursehawk_free`
   - `TELEGRAM_ADMIN_CHAT_ID`: your chat ID from step 3
   - `CUELINKS_TEMPLATE` (optional): your Cuelinks tracking link with `{url}` where the Udemy link goes
5. **First run.** Actions tab → Course Hawk → Run workflow, tick "Scan for new courses now".

## Settings

Filters, topics, sources, YouTube channels and slots are in `course_hawk/config.py`; the
curated courses are in `course_hawk/catalog.json`. `python -m course_hawk.diagnose` checks which
sources work from where it runs.

## Development

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
COURSE_HAWK_DRY_RUN=1 python -m course_hawk --scan-now   # logs posts instead of sending them
```
