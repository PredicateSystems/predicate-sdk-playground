### How to Run:
> python main.py

### Original Logs

python main.py
/Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/.venv/lib/python3.11/site-packages/imageio_ffmpeg/_utils.py:7: UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html. The pkg_resources package is slated for removal as early as 2025-11-30. Refrain from using this package or pin to Setuptools<81.
  from pkg_resources import resource_filename
[warn] Using sentience from site-packages: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/.venv/lib/python3.11/site-packages/sentience/__init__.py
       Python: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/.venv/bin/python
       If you expected the monorepo SDK, activate the demo venv and run:
         pip install -e ../sdk-python

`torch_dtype` is deprecated! Use `dtype` instead!
Loading checkpoint shards: 100%|████████████████████████████████████████████████████████████████| 2/2 [00:02<00:00,  1.15s/it]
⚠️  [Sentience] Found 1 un-uploaded trace(s) from previous runs
   Attempting to upload now...
☁️  [Sentience] Cloud tracing enabled (Pro tier)
Screenshots will be saved to: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/screenshots/20260115_223650

[2026-01-15 22:36:51] Starting Step 1: Navigate to login page
  [debug] Browser URL after navigation: https://sentience-sdk-playground.vercel.app/login
  [info] Waiting for login form hydration using eventually()...
  [info] Login form hydrated successfully
  [debug] Snapshot URL: https://sentience-sdk-playground.vercel.app/login
  [info] URL verified: https://sentience-sdk-playground.vercel.app/login
  [debug] Found 1 buttons, 2 textboxes:
    button: id=25 text='Sign in' disabled=None
    textbox: id=22 text='••••••••'
    textbox: id=19 text='username'
  [warn] Could not verify button is disabled initially - continuing anyway
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/screenshots/20260115_223650/scene1_Navigate_to_login_page.png
[2026-01-15 22:36:57] Step 1 PASS (5978ms): Navigate to login page
[2026-01-15 22:36:57] Step 1 completed with ok=True

[2026-01-15 22:36:57] Starting Step 2: Fill username field

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
  [debug] LLM response: 'CLICK(19)'
  [info] LLM chose element ID 19 for username field
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/screenshots/20260115_223650/scene2_Fill_username_field.png
[2026-01-15 22:37:10] Step 2 PASS (13324ms): Fill username field | typed=testuser
  tokens: prompt=413 completion=6 total=419
[2026-01-15 22:37:10] Step 2 completed with ok=True

[2026-01-15 22:37:10] Starting Step 3: Fill password field

--- Step 3: LLM compact prompt ---
22|textbox|••••••••|1184|0|2|-|0|
19|textbox|testuser|1173|0|1|-|0|
25|button|Sign in|573|0|2|-|0|
6|link|Login|0|0|0|-|0|vercel
9|link|Form|0|0|0|-|0|vercel
7|link|Profile|0|0|0|-|0|vercel
8|link|Dashboard|0|0|0|-|0|vercel
4|link|Local LLama Land|0|1|0|-|0|vercel
--- end compact prompt ---

  [debug] LLM response: 'CLICK(22)'
  [info] LLM chose element ID 22 for password field
  [info] Waiting for login button to become enabled...
  [debug] After filling fields, found 1 buttons:
    id=25 text='Sign in' disabled=None
  [info] Button is now ENABLED after filling both fields
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/screenshots/20260115_223650/scene3_Fill_password_field.png
[2026-01-15 22:37:29] Step 3 PASS (18890ms): Fill password field | password_filled
  tokens: prompt=422 completion=6 total=428
[2026-01-15 22:37:29] Step 3 completed with ok=True

[2026-01-15 22:37:29] Starting Step 4: Click login button

--- Step 4: LLM compact prompt ---
22|textbox|••••••••|1184|0|2|-|0|
19|textbox|testuser|1173|0|1|-|0|
25|button|Sign in|573|0|2|-|0|
6|link|Login|0|0|0|-|0|vercel
4|link|Local LLama Land|0|1|0|-|0|vercel
7|link|Profile|0|0|0|-|0|vercel
8|link|Dashboard|0|0|0|-|0|vercel
9|link|Form|0|0|0|-|0|vercel
--- end compact prompt ---

  LLM chose element ID 25 for login button
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/screenshots/20260115_223650/scene4_Click_login_button.png
[2026-01-15 22:37:43] Step 4 PASS (14049ms): Click login button | navigated_to=https://sentience-sdk-playground.vercel.app/profile
  tokens: prompt=430 completion=6 total=436
[2026-01-15 22:37:43] Step 4 completed with ok=True

[2026-01-15 22:37:43] Starting Step 5: Navigate to profile page
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/screenshots/20260115_223650/scene5_Navigate_to_profile_page.png
[2026-01-15 22:37:55] Step 5 PASS (11994ms): Navigate to profile page
[2026-01-15 22:37:55] Step 5 completed with ok=True

[2026-01-15 22:37:55] Starting Step 6: Extract username and email from profile
  [info] Waiting for profile card to load...

--- Step 6: LLM compact prompt ---
26|button|Edit profile|554|0|1|-|0|
19|button|Sign out|536|0|1|-|0|
17|link|Dashboard|156|0|1|-|0|vercel
18|link|Dashboard|156|0|1|-|0|vercel
7|link|Profile|0|0|0|-|0|vercel
6|link|Login|0|0|0|-|0|vercel
9|link|Form|0|0|0|-|0|vercel
8|link|Dashboard|0|0|0|-|0|vercel
4|link|Local LLama Land|0|1|0|-|0|vercel
--- end compact prompt ---

  [info] Extracted username: Your profile

This page intentionally loads content late.

Dashboard
Sign out
Profile
testuser
testu
  [info] Extracted email: Profile
testuser
testuser@localllama.land
Edit profile
  Screenshot saved: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/screenshots/20260115_223650/scene6_Extract_username_and_email_fro.png
[2026-01-15 22:38:16] Step 6 PASS (20979ms): Extract username and email from profile | username=Your profile

This page intentionally loads content late.

Dashboard
Sign out
Profile
testuser
testu | email=Profile
testuser
testuser@localllama.land
Edit profile
[2026-01-15 22:38:16] Step 6 completed with ok=True
✅ [Sentience] Trace uploaded successfully

=== Run Summary ===
run_id: 4097c10e-f5b1-4532-bef7-dad31f3d106b
success: True
duration_ms: 93757
tokens_total: StepTokenUsage(prompt_tokens=1265, completion_tokens=18, total_tokens=1283)

======================================================================
Generating video with token overlay...
======================================================================

Creating video from screenshots in /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/screenshots/20260115_223650...
Found 6 screenshots
  Processing scene1_Navigate_to_login_page.png...
  Processing scene2_Fill_username_field.png...
    Adding token overlay (419 tokens)...
  Processing scene3_Fill_password_field.png...
    Adding token overlay (428 tokens)...
  Processing scene4_Click_login_button.png...
    Adding token overlay (436 tokens)...
  Processing scene5_Navigate_to_profile_page.png...
  Processing scene6_Extract_username_and_email_fro.png...
  Creating summary screen...
  Concatenating clips...
  Writing video to /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/video/login_profile_20260115_223650.mp4...

✅ Video created: /Users/sentienceDEV/Code/Sentience/sentience-sdk-playground/login_profile_check/video/login_profile_20260115_223650.mp4
   Total duration: 25.0s
   Scenes: 7