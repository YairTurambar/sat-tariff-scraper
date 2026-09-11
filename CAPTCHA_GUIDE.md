# CAPTCHA Handling Guide

## Understanding the CAPTCHA Issue

The SAT portal uses a **CAPTCHA field** (`frmBuscar:txtKaptcha`) to prevent automated access. This guide explains how to work with the updated scraper that handles CAPTCHA automatically.

## How It Works Now

The updated `sat_scraper.py` includes **manual CAPTCHA handling**, which means:

1. ✅ Script automatically detects when CAPTCHA appears
2. ✅ Browser window stays visible and open
3. ✅ Script pauses and waits for you to solve it
4. ✅ Once solved, script automatically continues
5. ✅ No need to restart or manually enter HS codes again
6. ✅ You normally solve **one CAPTCHA per run**, not one per HS code

## Why Only One CAPTCHA Per Run

The portal re-arms the CAPTCHA every time a **blank** search form is loaded, but the
results page keeps the HS code field (`frmBuscar:txtCodigo`) and accepts another
search without a new CAPTCHA.

The catch is that opening "Derechos e impuestos" in place replaces that results
page, which used to cost one CAPTCHA per code. The scraper now renders the duties
view in a **throwaway second tab** (`extract_duties_in_new_tab()`), so the
validated results page survives and the next code can be searched straight away.

This is not a CAPTCHA bypass - you still solve the challenge yourself. It simply
avoids needlessly throwing the validated session away.

> If the browser ever gets knocked off the results page, `return_to_search()`
> reloads the form as a fallback, and that does require a fresh CAPTCHA.

## Usage

### Basic Usage (Recommended)

```bash
python main.py hs_codes.txt
```

The browser will:
- Open automatically
- Navigate to SAT portal
- Stop when CAPTCHA is detected
- Wait for you to solve it (up to 5 minutes)
- Continue automatically after solving

### How to Use with CAPTCHA

**Step 1: Start the Script**
```bash
python main.py hs_codes.txt
```

**Step 2: Watch for CAPTCHA Message**
You'll see in the terminal:
```
============================================================
⚠️  CAPTCHA DETECTED - Manual intervention required
============================================================
Please complete the CAPTCHA in the browser window:
1. A browser window is open with the SAT portal
2. Look for the CAPTCHA field
3. Solve the CAPTCHA and click search
4. The script will automatically continue after solving
============================================================
```

**Step 3: Solve CAPTCHA**
- Look at the open browser window
- Find the CAPTCHA field (usually with an image or text challenge)
- Solve the CAPTCHA (read the characters and enter them)
- Click the "Consultar" (Search) button

**Step 4: Script Continues Automatically**
- Once the CAPTCHA field disappears from the page, the script detects this
- Message shows: `✅ CAPTCHA solved! Continuing with data extraction...`
- Extraction proceeds automatically

## Configuration Options

Edit `main.py` or `config.py` to customize CAPTCHA handling:

```python
from sat_scraper import SATTariffScraper

# Enable manual CAPTCHA solving (default: True)
scraper = SATTariffScraper(
    headless=False,        # Keep browser visible
    manual_captcha=True    # Enable CAPTCHA detection
)

# Run with your HS codes
scraper.run(["0101210000", "0102210000"])
```

## Parameters Explained

| Parameter | Default | Description |
|-----------|---------|-------------|
| `headless` | `False` | If `True`, hides browser window (not recommended for CAPTCHA) |
| `manual_captcha` | `True` | If `True`, pauses for manual CAPTCHA entry |

**Important**: Keep `headless=False` so you can see and solve CAPTCHA!

## Timing & Limits

- **Wait Time**: 5 minutes (300 seconds) to solve CAPTCHA
- **How Often**: Once per run, not once per HS code
- **Auto-Detection**: Script checks whether the CAPTCHA field is still present every 1 second
- **Request Delay**: 2 seconds between HS code searches (respects server load)

If you need more time:
- Edit `CAPTCHA_TIMEOUT = 300` at the top of `sat_scraper.py`, or
- Pass it per run: `SATTariffScraper(captcha_timeout=600)`

## Troubleshooting

### Issue: "CAPTCHA solving timeout"
**Solution**: 
- The script waited 5 minutes but didn't detect solved CAPTCHA
- Options:
  1. Increase `CAPTCHA_TIMEOUT` in `sat_scraper.py`
  2. Make sure you clicked "Consultar" after solving
  3. Check that the CAPTCHA field is no longer shown on the page

### Issue: Browser closes after CAPTCHA
**Solution**: Make sure `headless=False` is set:
```python
scraper = SATTariffScraper(headless=False, manual_captcha=True)
```

### Issue: Script doesn't detect CAPTCHA
**Solution**:
1. Check browser developer tools (F12)
2. Find the CAPTCHA input field ID
3. Update selectors in `sat_scraper.py` line ~127-131

### Issue: Can't solve CAPTCHA in time
**Solution**: Increase the wait time in `sat_scraper.py`:
```python
CAPTCHA_TIMEOUT = 600  # 10 minutes instead of 5
```

## Advanced: Check for CAPTCHA Manually

If you want to check if CAPTCHA is being detected:

```python
from sat_scraper import SATTariffScraper

scraper = SATTariffScraper()
scraper.start_browser()
scraper.navigate_to_portal()

# Check if CAPTCHA is on page
if scraper.check_for_captcha():
    print("✓ CAPTCHA detected")
else:
    print("✗ No CAPTCHA found")
    
scraper.close_browser()
```

## Best Practices

✅ **DO:**
- Keep browser window visible (`headless=False`)
- Process one batch at a time
- Monitor the terminal for messages
- Take your time solving CAPTCHA

❌ **DON'T:**
- Close the browser before CAPTCHA is solved
- Use `headless=True` with manual CAPTCHA
- Set `manual_captcha=False` (will fail on CAPTCHA)

## Example Workflow

```bash
# 1. Create file with HS codes
echo "0101210000" > my_codes.txt
echo "0102210000" >> my_codes.txt

# 2. Run scraper
python main.py my_codes.txt

# 3. When CAPTCHA appears, solve it in browser
# (Watch terminal for confirmation)

# 4. Script continues automatically
# (Check terminal for progress)

# 5. Excel file is generated
# (sat_tariff_data.xlsx or your specified output file)
```

## Logging & Monitoring

To see detailed logs:

```bash
# Watch logs in real-time
tail -f scraper.log
```

Or check `scraper.log` file after execution for:
- ✓ CAPTCHA detection times
- ✓ Data extraction progress
- ✓ Any errors or warnings

## Support

For issues:
1. Check `scraper.log` for detailed error messages
2. Try updating selectors in `sat_scraper.py`
3. Test CAPTCHA detection manually first
4. Create a GitHub issue with logs attached

---

**Summary**: The script now handles CAPTCHA gracefully by pausing for your manual input and continuing automatically. This is the most reliable method! 🎯
