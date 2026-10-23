# Course Hawk

Finds free (100% off) Udemy coupons, checks on Udemy that each one really shows ₹0, filters out weak
or off-topic courses, and sends you a preview in Telegram. You tap **Approve**, and it posts to your
channel in the next time slot. Posts whose coupon later ends are marked **EXPIRED**.

Everything runs free on GitHub Actions (public repo) with no server or database: state lives in
`state/state.json`, which each run commits back.

## How a run works

Every 15 minutes the workflow runs `python -m course_hawk`, which:

1. Reads your button taps and messages to the bot.
2. Posts the best queued courses if a post slot is due (08:00, 12:30, 17:30, 20:00, 21:30 IST).
   Each course's price is checked again right before posting.
3. Rechecks posts from the last 5 days every 3 hours and marks ended coupons as expired.
4. At 07:30, 12:00, 17:00 and 21:00 IST, scans the sources and sends up to 10 previews.

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

Filters, topics, sources and slots are in `course_hawk/config.py`.

## Development

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
COURSE_HAWK_DRY_RUN=1 python -m course_hawk --scan-now   # logs posts instead of sending them
```
