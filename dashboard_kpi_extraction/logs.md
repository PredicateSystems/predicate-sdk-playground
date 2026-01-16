### How to Run
> python main.py

### Original Logs
/Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/.venv/lib/python3.11/site-packages/imageio_ffmpeg/_utils.py:7: UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html. The pkg_resources package is slated for removal as early as 2025-11-30. Refrain from using this package or pin to Setuptools<81.
  from pkg_resources import resource_filename
[warn] Using sentience from site-packages: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/.venv/lib/python3.11/site-packages/sentience/__init__.py
       Python: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/.venv/bin/python
       If you expected the monorepo SDK, activate the demo venv and run:
         pip install -e ../sdk-python

`torch_dtype` is deprecated! Use `dtype` instead!
Loading checkpoint shards: 100%|████████████████████████████████████| 2/2 [00:02<00:00,  1.45s/it]
⚠️  [Sentience] Found 1 un-uploaded trace(s) from previous runs
   Attempting to upload now...
☁️  [Sentience] Cloud tracing enabled (Pro tier)
Screenshots will be saved to: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444

[2026-01-15 23:04:46] Starting Step 1: Navigate to login page
  [debug] Browser URL after navigation: https://sentience-sdk-playground.vercel.app/login
  [info] Waiting for login form hydration...
  [info] Login form hydrated successfully
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene1_Navigate_to_login_page.png
[2026-01-15 23:04:52] Step 1 PASS (6280ms): Navigate to login page
[2026-01-15 23:04:52] Step 1 completed with ok=True

[2026-01-15 23:04:52] Starting Step 2: Fill username field

--- Step 2: LLM compact prompt ---
22|textbox|••••••••|1184|0|2|-|0|
19|textbox|username|1173|0|1|-|0|
25|button|Sign in|573|0|2|-|0|
6|link|Login|0|0|0|-|0|vercel
8|link|Dashboard|0|0|0|-|0|vercel
9|link|Form|0|0|0|-|0|vercel
7|link|Profile|0|0|0|-|0|vercel
4|link|Local LLama Land|0|1|0|-|0|vercel
--- end compact prompt ---

The following generation flags are not valid and may be ignored: ['top_p', 'top_k']. Set `TRANSFORMERS_VERBOSITY=info` for more details.
  [info] LLM chose element ID 19 for username field
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene2_Fill_username_field.png
[2026-01-15 23:05:05] Step 2 PASS (13244ms): Fill username field | typed=testuser
  tokens: prompt=319 completion=6 total=325
[2026-01-15 23:05:05] Step 2 completed with ok=True

[2026-01-15 23:05:05] Starting Step 3: Fill password field
  [info] LLM chose element ID 22 for password field
  [info] Waiting for login button to become enabled...
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene3_Fill_password_field.png
[2026-01-15 23:05:24] Step 3 PASS (18846ms): Fill password field | password_filled
  tokens: prompt=327 completion=6 total=333
[2026-01-15 23:05:24] Step 3 completed with ok=True

[2026-01-15 23:05:24] Starting Step 4: Click login button
  [info] LLM chose element ID 25 for login button
  [info] After login, URL: https://sentience-sdk-playground.vercel.app/profile
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene4_Click_login_button.png
[2026-01-15 23:05:38] Step 4 PASS (13760ms): Click login button | navigated_to=https://sentience-sdk-playground.vercel.app/profile
  tokens: prompt=325 completion=6 total=331
[2026-01-15 23:05:38] Step 4 completed with ok=True

[2026-01-15 23:05:38] Starting Step 5: Navigate to dashboard page
  [info] LLM chose element ID 17 for dashboard link
  [info] Dashboard URL verified: https://sentience-sdk-playground.vercel.app/dashboard
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene5_Navigate_to_dashboard_page.png
[2026-01-15 23:06:07] Step 5 PASS (28949ms): Navigate to dashboard page
  tokens: prompt=331 completion=6 total=337
[2026-01-15 23:06:07] Step 5 completed with ok=True

[2026-01-15 23:06:07] Starting Step 6: Wait for KPI cards to load
  [info] Waiting for KPI cards to load...
  [info] KPI cards loaded successfully
  [debug] Snapshot has 34 elements
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene6_Wait_for_KPI_cards_to_load.png
[2026-01-15 23:06:18] Step 6 PASS (11228ms): Wait for KPI cards to load
[2026-01-15 23:06:18] Step 6 completed with ok=True

[2026-01-15 23:06:18] Starting Step 7: Extract KPI values

--- Step 7: Dashboard snapshot ---
35|button|Enable live updates|578|0|2|-|0|
8|link|Dashboard|0|0|0|-|0|vercel
9|link|Form|0|0|0|-|0|vercel
6|link|Login|0|0|0|-|0|vercel
7|link|Profile|0|0|0|-|0|vercel
4|link|Local LLama Land|0|1|0|-|0|vercel
--- end snapshot ---

  [info] Extracted KPIs:
    Llama Coins: value=128 (label_found=True)
    Active Herds: value=7 (label_found=True)
    Messages: value=3 (label_found=True)
  [info] Successfully extracted 3/3 KPI values
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene7_Extract_KPI_values.png
[2026-01-15 23:06:24] Step 7 PASS (5601ms): Extract KPI values | Llama Coins=128 | Active Herds=7 | Messages=3
[2026-01-15 23:06:24] Step 7 completed with ok=True

[2026-01-15 23:06:24] Starting Step 8: Verify event table loaded
  [info] Waiting for event table to load...
  [info] Found events: ['Signed in', 'Viewed profile']
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene8_Verify_event_table_loaded.png
[2026-01-15 23:06:35] Step 8 PASS (11166ms): Verify event table loaded | events=['Signed in', 'Viewed profile']
[2026-01-15 23:06:35] Step 8 completed with ok=True

[2026-01-15 23:06:35] Starting Step 9: Extract KPIs during DOM churn (stress test)
  [info] Enabling live updates to test DOM churn resilience...

--- Step 9: Finding live updates button ---
35|button|Enable live updates|578|0|2|-|0|
6|link|Login|0|0|0|-|0|vercel
4|link|Local LLama Land|0|1|0|-|0|vercel
8|link|Dashboard|0|0|0|-|0|vercel
7|link|Profile|0|0|0|-|0|vercel
9|link|Form|0|0|0|-|0|vercel
--- end snapshot ---

  [info] Found live updates button: id=35 text='Enable live updates'
  [info] Clicking button id=35 to enable live mode...
  [info] Waiting 2s for DOM churn to accumulate...
  [info] Re-extracting KPIs during DOM churn...

--- Step 9: Snapshot during DOM churn ---
35|button|Disable live updates|579|0|2|-|0|
9|link|Form|0|0|0|-|0|vercel
6|link|Login|0|0|0|-|0|vercel
8|link|Dashboard|0|0|0|-|0|vercel
7|link|Profile|0|0|0|-|0|vercel
4|link|Local LLama Land|0|1|0|-|0|vercel
--- end snapshot ---

  [info] During DOM churn, extracted 3/3 KPI values:
    Llama Coins: value=128 (label_found=True)
    Active Herds: value=7 (label_found=True)
    Messages: value=3 (label_found=True)
  [info] Found 1 'Live ping' events (proves DOM churn is active)
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444/scene9_Extract_KPIs_during_DOM_churn_.png
[2026-01-15 23:06:55] Step 9 PASS (19454ms): Extract KPIs during DOM churn (stress test) | churn_events=1 | Llama Coins=128 | Active Herds=7 | Messages=3
[2026-01-15 23:06:55] Step 9 completed with ok=True
✅ [Sentience] Trace uploaded successfully

=== Run Summary ===
run_id: 6b1be953-f913-480c-bb2b-87917fcae6f8
success: True
duration_ms: 138085
tokens_total: StepTokenUsage(prompt_tokens=1302, completion_tokens=24, total_tokens=1326)

======================================================================
Generating video with token overlay...
======================================================================

Creating video from screenshots in /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/screenshots/20260115_230444...
Found 9 screenshots
  Processing scene1_Navigate_to_login_page.png...
  Processing scene2_Fill_username_field.png...
    Adding token overlay (325 tokens)...
  Processing scene3_Fill_password_field.png...
    Adding token overlay (333 tokens)...
  Processing scene4_Click_login_button.png...
    Adding token overlay (331 tokens)...
  Processing scene5_Navigate_to_dashboard_page.png...
    Adding token overlay (337 tokens)...
  Processing scene6_Wait_for_KPI_cards_to_load.png...
  Processing scene7_Extract_KPI_values.png...
  Processing scene8_Verify_event_table_loaded.png...
  Processing scene9_Extract_KPIs_during_DOM_churn_.png...
  Creating summary screen...
  Concatenating clips...
  Writing video to /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/video/dashboard_kpi_20260115_230444.mp4...

✅ Video created: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/dashboard_kpi_extraction/video/dashboard_kpi_20260115_230444.mp4
   Total duration: 36.0s
   Scenes: 10