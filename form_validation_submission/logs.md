## How to Run
> python main.py

## Original Logs

/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/.venv/lib/python3.11/site-packages/imageio_ffmpeg/_utils.py:7: UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html. The pkg_resources package is slated for removal as early as 2025-11-30. Refrain from using this package or pin to Setuptools<81.
  from pkg_resources import resource_filename
[warn] Using sentience from site-packages: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/.venv/lib/python3.11/site-packages/sentience/__init__.py
       Python: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/.venv/bin/python
       If you expected the monorepo SDK, activate the demo venv and run:
         pip install -e ../sdk-python

`torch_dtype` is deprecated! Use `dtype` instead!
Loading checkpoint shards: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████| 2/2 [00:03<00:00,  1.62s/it]
  LLM initialized: Qwen/Qwen2.5-3B-Instruct
⚠️  [Sentience] Found 1 un-uploaded trace(s) from previous runs
   Attempting to upload now...
☁️  [Sentience] Cloud tracing enabled (Pro tier)
Screenshots will be saved to: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604
[2026-01-16 16:46:04] Starting Demo 5: Form Validation + Submission
  Model: Qwen/Qwen2.5-3B-Instruct
  Use API: True
  Test email: testuser@localllama.land
  Test name: Llama Rider
  Test plan: pro
  Tracer run_id: c414b573-b688-4b36-85f3-291b6d73e2cd

[2026-01-16 16:46:06] Starting Step 1: Navigate to onboarding form page
  [debug] Browser URL after navigation: https://sentience-sdk-playground.vercel.app/forms/onboarding
  [info] Waiting for onboarding form hydration...
  [info] Onboarding form hydrated successfully
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene1_Navigate_to_onboarding_form_pa.png
[2026-01-16 16:46:12] Step 1 PASS (6078ms): Navigate to onboarding form page
[2026-01-16 16:46:12] Step 1 completed with ok=True

[2026-01-16 16:46:12] Starting Step 2: Fill email field

--- Step 2: LLM compact prompt ---
26|textbox|you@localllama.land|1182|0|2|-|0|
29|button|Back|568|0|2|-|0|
30|button|Next|567|0|2|-|0|
10|link|Login|0|0|0|-|0|vercel
13|link|Form|0|0|0|-|0|vercel
12|link|Dashboard|0|0|0|-|0|vercel
11|link|Profile|0|0|0|-|0|vercel
9|link|About|0|0|0|-|0|vercel
4|link|Local Llama Land|0|1|0|-|0|vercel
--- end compact prompt ---

The following generation flags are not valid and may be ignored: ['top_p', 'top_k']. Set `TRANSFORMERS_VERBOSITY=info` for more details.
  [info] LLM chose element ID 26 for email field
  [warn] Could not verify email value
  [info] Waiting for Next button to become enabled...
  [info] Next button is now ENABLED after entering valid email
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene2_Fill_email_field.png
[2026-01-16 16:46:38] Step 2 PASS (26118ms): Fill email field | email=testuser@localllama.land
  tokens: prompt=430 completion=6 total=436
[2026-01-16 16:46:38] Step 2 completed with ok=True

[2026-01-16 16:46:38] Starting Step 3: Click Next to Step 2

--- Step 3: LLM compact prompt ---
26|textbox|testuser@localllama.land|1182|0|2|-|0|
29|button|Back|568|0|2|-|0|
30|button|Next|567|0|2|-|0|
4|link|Local Llama Land|0|1|0|-|0|vercel
10|link|Login|0|0|0|-|0|vercel
12|link|Dashboard|0|0|0|-|0|vercel
11|link|Profile|0|0|0|-|0|vercel
9|link|About|0|0|0|-|0|vercel
13|link|Form|0|0|0|-|0|vercel
--- end compact prompt ---

  [info] LLM chose element ID 30 for Next button
  [info] Successfully transitioned to Step 2
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene3_Click_Next_to_Step_2.png
[2026-01-16 16:46:57] Step 3 PASS (18928ms): Click Next to Step 2
  tokens: prompt=412 completion=6 total=418
[2026-01-16 16:46:57] Step 3 completed with ok=True

[2026-01-16 16:46:57] Starting Step 4: Fill display name field

--- Step 4: LLM compact prompt ---
26|textbox|Llama Rider|1182|0|2|-|0|
29|button|Back|568|0|2|-|0|
30|button|Next|567|0|2|-|0|
10|link|Login|0|0|0|-|0|vercel
13|link|Form|0|0|0|-|0|vercel
12|link|Dashboard|0|0|0|-|0|vercel
9|link|About|0|0|0|-|0|vercel
4|link|Local Llama Land|0|1|0|-|0|vercel
11|link|Profile|0|0|0|-|0|vercel
--- end compact prompt ---

  [info] LLM chose element ID 26 for display name field
  [warn] Could not verify name value
  [info] Waiting for Next button to become enabled...
  [info] Next button is now ENABLED after entering valid name
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene4_Fill_display_name_field.png
[2026-01-16 16:47:22] Step 4 PASS (24933ms): Fill display name field | name=Llama Rider
  tokens: prompt=421 completion=6 total=427
[2026-01-16 16:47:22] Step 4 completed with ok=True

[2026-01-16 16:47:22] Starting Step 5: Click Next to Step 3

--- Step 5: LLM compact prompt ---
26|textbox|Llama Rider|1182|0|2|-|0|
29|button|Back|568|0|2|-|0|
30|button|Next|567|0|2|-|0|
4|link|Local Llama Land|0|1|0|-|0|vercel
10|link|Login|0|0|0|-|0|vercel
12|link|Dashboard|0|0|0|-|0|vercel
11|link|Profile|0|0|0|-|0|vercel
9|link|About|0|0|0|-|0|vercel
13|link|Form|0|0|0|-|0|vercel
--- end compact prompt ---

  [info] Successfully transitioned to Step 3
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene5_Click_Next_to_Step_3.png
[2026-01-16 16:47:41] Step 5 PASS (18879ms): Click Next to Step 3
  tokens: prompt=405 completion=6 total=411
[2026-01-16 16:47:41] Step 5 completed with ok=True

[2026-01-16 16:47:41] Starting Step 6: Select plan (radio)

--- Step 6: LLM compact prompt ---
34|button|Back|567|0|2|-|0|
35|button|Next|566|0|2|-|0|
31|checkbox|on|79|0|2|-|0|
29|radio|pro|79|0|2|-|0|
27|radio|free|78|0|2|-|0|
10|link|Login|0|0|0|-|0|vercel
4|link|Local Llama Land|0|1|0|-|0|vercel
12|link|Dashboard|0|0|0|-|0|vercel
9|link|About|0|0|0|-|0|vercel
13|link|Form|0|0|0|-|0|vercel
11|link|Profile|0|0|0|-|0|vercel
--- end compact prompt ---

  [info] LLM chose element ID 29 for pro plan
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene6_Select_plan_(radio).png
[2026-01-16 16:47:59] Step 6 PASS (18142ms): Select plan (radio) | plan=pro
  tokens: prompt=448 completion=6 total=454
[2026-01-16 16:47:59] Step 6 completed with ok=True

[2026-01-16 16:47:59] Starting Step 7: Check Terms checkbox

--- Step 7: LLM compact prompt ---
34|button|Back|567|0|2|-|0|
35|button|Next|566|0|2|-|0|
31|checkbox|on|79|0|2|-|0|
29|radio|pro|79|0|2|-|0|
27|radio|free|78|0|2|-|0|
10|link|Login|0|0|0|-|0|vercel
13|link|Form|0|0|0|-|0|vercel
12|link|Dashboard|0|0|0|-|0|vercel
9|link|About|0|0|0|-|0|vercel
11|link|Profile|0|0|0|-|0|vercel
4|link|Local Llama Land|0|1|0|-|0|vercel
--- end compact prompt ---

  [info] LLM chose element ID 31 for Terms checkbox
  [info] Waiting for Next button to become enabled...
  [info] Next button is now ENABLED after selecting plan and checking terms
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene7_Check_Terms_checkbox.png
[2026-01-16 16:48:23] Step 7 PASS (23357ms): Check Terms checkbox | terms_checked
  tokens: prompt=446 completion=6 total=452
[2026-01-16 16:48:23] Step 7 completed with ok=True

[2026-01-16 16:48:23] Starting Step 8: Click Next to Step 4 (Review)

--- Step 8: LLM compact prompt ---
34|button|Back|567|0|2|-|0|
35|button|Next|566|0|2|-|0|
31|checkbox|on|79|0|2|-|0|
29|radio|pro|79|0|2|-|0|
27|radio|free|78|0|2|-|0|
11|link|Profile|0|0|0|-|0|vercel
12|link|Dashboard|0|0|0|-|0|vercel
10|link|Login|0|0|0|-|0|vercel
9|link|About|0|0|0|-|0|vercel
4|link|Local Llama Land|0|1|0|-|0|vercel
13|link|Form|0|0|0|-|0|vercel
--- end compact prompt ---

  [info] Successfully transitioned to Step 4 (Review)
  [info] Review section is visible
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene8_Click_Next_to_Step_4_(Review).png
[2026-01-16 16:48:42] Step 8 PASS (19082ms): Click Next to Step 4 (Review)
  tokens: prompt=437 completion=6 total=443
[2026-01-16 16:48:42] Step 8 completed with ok=True

[2026-01-16 16:48:42] Starting Step 9: Click Submit button

--- Step 9: LLM compact prompt ---
36|button|Submit|570|0|3|-|0|
35|button|Back|564|0|3|-|0|
13|link|Form|0|0|0|-|0|vercel
4|link|Local Llama Land|0|1|0|-|0|vercel
10|link|Login|0|0|0|-|0|vercel
11|link|Profile|0|0|0|-|0|vercel
9|link|About|0|0|0|-|0|vercel
12|link|Dashboard|0|0|0|-|0|vercel
--- end compact prompt ---

  [info] LLM chose element ID 36 for Submit button
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene9_Click_Submit_button.png
[2026-01-16 16:48:56] Step 9 PASS (14311ms): Click Submit button
  tokens: prompt=383 completion=6 total=389
[2026-01-16 16:48:56] Step 9 completed with ok=True

[2026-01-16 16:48:56] Starting Step 10: Verify success message
  [info] Waiting for success message...
  [info] Success message is visible!
  Screenshot saved: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604/scene10_Verify_success_message.png
[2026-01-16 16:49:02] Step 10 PASS (5485ms): Verify success message
[2026-01-16 16:49:02] Step 10 completed with ok=True
✅ [Sentience] Trace uploaded successfully

=== Run Summary ===
run_id: c414b573-b688-4b36-85f3-291b6d73e2cd
success: True
duration_ms: 184952
tokens_total: StepTokenUsage(prompt_tokens=3382, completion_tokens=48, total_tokens=3430)

======================================================================
Generating video with token overlay...
======================================================================

Creating video from screenshots in /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/screenshots/20260116_164604...
Found 10 screenshots
  Processing scene10_Verify_success_message.png...
  Processing scene1_Navigate_to_onboarding_form_pa.png...
    Adding token overlay (436 tokens)...
  Processing scene2_Fill_email_field.png...
    Adding token overlay (418 tokens)...
  Processing scene3_Click_Next_to_Step_2.png...
    Adding token overlay (427 tokens)...
  Processing scene4_Fill_display_name_field.png...
    Adding token overlay (411 tokens)...
  Processing scene5_Click_Next_to_Step_3.png...
    Adding token overlay (454 tokens)...
  Processing scene6_Select_plan_(radio).png...
    Adding token overlay (452 tokens)...
  Processing scene7_Check_Terms_checkbox.png...
    Adding token overlay (443 tokens)...
  Processing scene8_Click_Next_to_Step_4_(Review).png...
    Adding token overlay (389 tokens)...
  Processing scene9_Click_Submit_button.png...
  Creating summary screen...
  Concatenating clips...
  Writing video to /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/video/form_validation_20260116_164604.mp4...

✅ Video created: /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/form_validation_submission/video/form_validation_20260116_164604.mp4
   Total duration: 39.0s
   Scenes: 11