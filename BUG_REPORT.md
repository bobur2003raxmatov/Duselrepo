# 🐛 Comprehensive Code Review - Bugs & Issues Found

## CRITICAL ISSUES 🚨

### 1. **Bot Token Hardcoded in config.py (SECURITY)**
**Location:** `config.py:3`
```python
TOKEN = os.environ.get("TOKEN", "8465121120:AAH8Gz0qKC-S0RCe7n8PswzCMMu-Igd4qx8")
```
**Problem:** Real bot token is exposed in the source code. This should NEVER be in the repo.
**Fix:** Remove the default token or use an empty string
```python
TOKEN = os.environ.get("TOKEN", "")
if not TOKEN:
    raise ValueError("TOKEN environment variable is required")
```

### 2. **Admin Xodimlar List Has No Clickable Profiles**
**Location:** `handlers.py:967-972` and `keyboards.py:100-108`
**Problem:** When admin presses "👥 Xodimlar", it shows a list of employees with pagination buttons only. There's NO way to click on individual employees to view their profiles. The xodimlar_page_inline() keyboard only has navigation buttons (Oldingi/Keyingi), not profile buttons.
**Expected:** Like search_results_kb which shows each employee as a clickable button
**Fix:** Modify xodimlar_page_inline() to return inline buttons for each employee with callback_data like `xodim_profil_{user_id}`:
```python
def xodimlar_page_inline(rows: list, page: int) -> InlineKeyboardMarkup:
    total = len(rows)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    
    buttons = []
    for r in rows[start:end]:
        buttons.append([InlineKeyboardButton(
            f"👤 {r[0]} — {r[1]} | {r[2]}",
            callback_data=f"xodim_profil_{r[4]}",
        )])
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Oldingi", callback_data=f"xod_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("Keyingi ▶️", callback_data=f"xod_page_{page + 1}"))
    if nav:
        buttons.append(nav)
    
    return InlineKeyboardMarkup(buttons)
```

---

## HIGH PRIORITY ISSUES ⚠️

### 3. **_send_xodimlar_page Missing Filial in Display**
**Location:** `handlers.py:956-963`
**Problem:** Shows ism, lavozim, kod but NOT filial
```python
matn += f"👤 *{em(r[0])}* | {em(r[1])} | Kod: `{em(r[3])}` | ID: `{r[4]}`\n"
```
Should include r[2] (filial):
```python
matn += f"👤 *{em(r[0])}* | {em(r[1])} | {em(r[2])} | Kod: `{em(r[3])}` | ID: `{r[4]}`\n"
```

### 4. **Unsafe Callback Data Parsing**
**Location:** Multiple callbacks - Examples:
- `handlers.py:839`: `group_id = int(data.split("_")[2])` 
- `handlers.py:811`: `yulduz = int(parts[2])`
- `handlers.py:876`: `group_id = int(data.split("_")[2])`

**Problem:** If callback_data is malformed (e.g., `"bir_tasd_"` without a group_id), this will crash with IndexError. No validation of the split results.
**Fix:** Add safe parsing:
```python
def safe_callback_int(data: str, sep: str = "_", index: int = -1) -> int | None:
    try:
        parts = data.split(sep)
        return int(parts[index])
    except (IndexError, ValueError):
        return None
```

### 5. **Missing em() Escaping in Some Places**
**Location:** Multiple locations - Examples:
- `handlers.py:668`: Display of filial not escaped
- `handlers.py:908`: Period display in _send_filial_leaderboard

**Problem:** User data should always be escaped to prevent Markdown injection
**Fix:** Use em() for all user-provided strings in Markdown mode

---

## MEDIUM PRIORITY ISSUES 📋

### 6. **_cb_group_action Missing Urgency Display**
**Location:** `handlers.py:672-709`
**Problem:** When admin clicks "🔄 Jarayonda" or "✅ Bajarildi" for a group, the message to the user doesn't show the urgency level that was set. Should remind them what urgency level was assigned.
**Fix:** Query urgency from DB and include in message

### 7. **Checker Timeout Job Doesn't Cancel on Completion**
**Location:** `handlers.py:443-447`
**Problem:** When checker approves/rejects before timeout (30 min), the scheduled timeout job still fires and sends an alert. Need to cancel it.
**Fix:** Cancel the job when checker responds:
```python
# In bir_tasd_ and bir_rad_ callbacks:
for j in context.job_queue.get_jobs_by_name(f"checker_timeout_{group_id}"):
    j.schedule_removal()
```

### 8. **SLA Schedule Not Cancelled When Group Completes**
**Location:** `handlers.py:449`, `utils.py:44-55`
**Problem:** SLA reminder jobs (15 & 30 min) are scheduled but never cancelled when group completes before timeout
**Fix:** Cancel jobs when group marked as "bajarildi":
```python
# In _cb_group_action after updating to "bajarildi":
for i in [1, 2]:
    for j in context.job_queue.get_jobs_by_name(f"sla_{group_id}_{i}"):
        j.schedule_removal()
```

### 9. **Missing Error Handling in admin_guruh_javob**
**Location:** `handlers.py:558-567`
**Problem:** Only has try/except at outer level. Inner copy() operation could fail and leaves the admin with no feedback
**Fix:** Add proper error messages to user

### 10. **get_latest_group_fwd_id Returns None Silently**
**Location:** `handlers.py:788, utils.py:106`
**Problem:** In urgency_timeout_job and callback handler, if get_latest_group_fwd_id returns None, the forward is skipped with no log. This is OK but could be confusing.
**Current:** Line 791-793 handles it but silently. OK but could log warning.

---

## LOW PRIORITY ISSUES 💡

### 11. **Inconsistent em() Usage Pattern**
**Location:** Throughout handlers.py
**Problem:** Some places use em() for user data, some don't. Inconsistent defensive programming.
**Examples:**
- Line 254: `f"👤 Ism: {d['ism']}"` - not escaped
- Line 668: `f"👤 *{em(r[0])}*"` - escaped

**Recommendation:** Always escape user input in parse_mode="Markdown" context

### 12. **Database Query Missing Status Check**
**Location:** `database.py:723`
```python
LEFT JOIN xodimlar c ON c.user_id = b.checker_id
```
**Problem:** Should filter to c.status='approved' to not count blocked/pending checkers
**Fix:**
```python
LEFT JOIN xodimlar c ON c.user_id = b.checker_id AND c.status='approved'
```

### 13. **weekly_report_job Has Potential Division by Zero**
**Location:** `utils.py:168`
```python
stars = ("⭐" * round(avg_r)) if avg_r else "—"
```
**Problem:** avg_r could be 0.0 which is falsy, shows "—" instead of "". Better to check `avg_r is not None`:
```python
stars = ("⭐" * round(avg_r)) if avg_r else ""
```

### 14. **Chat ID Parameter Type Mismatch**
**Location:** `utils.py:17, 58`
**Problem:** GROUP_CHAT_ID is negative int (-1003802115020) but sent to context.bot as chat_id. PTB handles it but should be consistent.
**Note:** Not a bug, PTB handles both int and str, but worth noting.

### 15. **Missing Pagination in blocked/pending xodimlar lists**
**Location:** `handlers.py:976-987, 991-999`
**Problem:** admin_kutilayotganlar and admin_bloklanganlar loop and send individual messages for each (could be dozens). Should use pagination like admin_xodimlar.
**Current:** Sends N messages (bad UX)
**Fix:** Use pagination with page navigation

### 16. **No Validation for Filial/Lavozim in Profile Edit**
**Location:** Need to check if edit handler validates
**Problem:** When editing agent's lavozim/filial via biriktirish system, should validate against LAVOZIMLAR and FILIALLAR lists

### 17. **Job Names Not Unique Per Group**
**Location:** `handlers.py:440, 443-447`
**Problem:** 
```python
name=f"urgency_{group_id}",  # This is unique ✓
# But checker_timeout job has no name, so can't be cancelled!
context.job_queue.run_once(checker_timeout_job, when=CHECKER_TIMEOUT_SEC, data={...})
```
**Fix:** Add names to all scheduled jobs:
```python
name=f"checker_timeout_{group_id}",
name=f"sla_{group_id}_{reminder}",
```

---

## CODE QUALITY ISSUES 🔍

### 18. **em() Function Only Takes String, Could Handle None Better**
**Location:** `handlers.py:39-41`
```python
def em(text) -> str:
    return escape_markdown(str(text), version=1)
```
**Problem:** Converts None to "None" string. Better to handle explicitly:
```python
def em(text) -> str:
    if text is None:
        return "—"
    return escape_markdown(str(text), version=1)
```

### 19. **Magic Number PAGE_SIZE Used Directly**
**Location:** `handlers.py:664, 958, etc`
**Problem:** PAGE_SIZE=10 used in multiple calculations. Should always import from config.
**Status:** Already correct (imports PAGE_SIZE), no issue.

### 20. **Biriktir_detail_kb Missing Back Button Context**
**Location:** `keyboards.py:186-212`
**Problem:** When viewing agent detail in biriktirish, there's no "Back" button to go to list if user scrolls down. Have to scroll up to see the back navigation. Actually checking... there IS a back button at line 211. OK.

---

## SUMMARY TABLE

| Issue | Severity | Type | Status |
|-------|----------|------|--------|
| Token Hardcoded | CRITICAL | Security | ❌ |
| Xodimlar List No Profiles | CRITICAL | UX/Feature | ❌ |
| Filial Missing in Display | HIGH | UX | ❌ |
| Unsafe Callback Parsing | HIGH | Stability | ⚠️ |
| Missing em() Escaping | HIGH | Security | ⚠️ |
| Urgency Not Shown on Update | MEDIUM | UX | ❌ |
| Checker Timeout Not Cancelled | MEDIUM | Logic | ❌ |
| SLA Jobs Not Cancelled | MEDIUM | Logic | ❌ |
| Missing Pagination in Blocked List | MEDIUM | UX | ❌ |
| Missing Job Names | MEDIUM | Logic | ⚠️ |

**Legend:** ❌ = Bug, ⚠️ = Partial/Minor, ✅ = Not a bug
