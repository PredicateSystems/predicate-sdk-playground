"""
Demo 1: Predicate SDK + LLM Agent for Google Search

Simple test:
1. Navigate to Google
2. Search for "visiting japan"
3. Click a non-ad result
"""
import os
import sys
import time
import json
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from predicate import PredicateBrowser, snapshot, click_rect
from llm_agent import LLMAgent
from token_tracker import TokenTracker
from bbox_visualizer import visualize_api_elements
from video_generator_simple import create_demo_video


def filter_elements(snapshot_data, exclude_roles):
    """Filter out elements with specific roles to reduce token usage"""
    filtered_data = snapshot_data.copy()
    original_count = len(snapshot_data.get('elements', []))

    filtered_elements = [
        elem for elem in snapshot_data.get('elements', [])
        if elem.get('role') not in exclude_roles
    ]

    filtered_data['elements'] = filtered_elements
    filtered_count = len(filtered_elements)

    print(f"  Element filtering: {original_count} -> {filtered_count} elements (excluded roles: {exclude_roles})")

    return filtered_data


def main():
    # Load environment variables
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
    openai_api_key = os.getenv('OPENAI_API_KEY')
    predicate_api_key = os.getenv('PREDICATE_API_KEY')

    if not openai_api_key:
        print("ERROR: OPENAI_API_KEY not found in .env file")
        return

    # Initialize tracker and agent
    tracker = TokenTracker("Google Search Demo 1: SDK + LLM")
    agent = LLMAgent(api_key=openai_api_key, tracker=tracker)

    # Screenshot directory with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_screenshots_dir = os.path.join(os.path.dirname(__file__), 'screenshots')
    screenshots_dir = os.path.join(base_screenshots_dir, timestamp)
    os.makedirs(screenshots_dir, exist_ok=True)
    print(f"Screenshots will be saved to: {screenshots_dir}")

    print("\n" + "="*70)
    print("DEMO 1: Predicate SDK + LLM - Google Search")
    print("="*70)

    with PredicateBrowser(api_key=predicate_api_key, headless=False) as browser:
        # Set viewport size
        browser.page.set_viewport_size({"width": 1920, "height": 1080})

        # =================================================================
        # SCENE 1: Navigate to Google & Find Search Box
        # =================================================================
        print("\n[Scene 1] Navigating to Google.com...")
        browser.page.goto("https://www.google.com", wait_until="domcontentloaded")
        time.sleep(2)

        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene1_google_home.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Get snapshot using API (WASM extension issue fixed)
        print("Getting snapshot from API...")
        snap = snapshot(browser, screenshot=False, use_api=True)
        snapshot_data = snap.model_dump()
        print(f"API returned {len(snapshot_data.get('elements', []))} elements")

        # Save snapshot JSON
        with open(os.path.join(screenshots_dir, "sdk_scene1_data.json"), 'w') as f:
            json.dump(snapshot_data, f, indent=2)

        # Visualize API elements with bounding boxes
        if snapshot_data.get('elements'):
            print("Visualizing elements with bounding boxes...")
            visualize_api_elements(screenshot_path, snapshot_data)

        # Scene 1 optimization: Filter out everything except search-related inputs
        print("Applying Scene 1 element filtering...")
        filtered_data = filter_elements(snapshot_data, exclude_roles=[
            "img", "image", "button", "link", "span", "div",
            "svg", "path", "g", "rect", "circle"
        ])

        # Ask LLM to find search bar
        prompt = """You are an AI agent controlling a web browser.

Current Task: Find the search input field on Google homepage.

Instructions:
1. Analyze the elements array
2. Find the search input field (likely role="textbox" or role="searchbox" or role="combobox")
3. Look for elements in the top area (bbox.y < 400)
4. Prioritize elements that are in_viewport and not is_occluded
5. Return the element ID and bbox coordinates

Response Format:
{
  "reasoning": "brief explanation of why you selected this element",
  "element_id": <id>,
  "bbox": {"x": <x>, "y": <y>, "width": <w>, "height": <h>},
  "action": "click"
}"""

        # Check if we have elements to analyze
        if not filtered_data.get('elements'):
            print("❌ ERROR: No elements found after filtering. Cannot proceed.")
            print("This might be due to:")
            print("  1. Google showing a consent dialog")
            print("  2. API filtering too aggressively")
            print("  3. Page not fully loaded")
            return

        result = agent.analyze_snapshot(filtered_data, prompt, "Scene 1: Find Search Box")

        # Validate result
        if not result.get('bbox') or result['bbox'].get('x') is None:
            print("❌ ERROR: LLM did not return valid coordinates")
            print(f"LLM response: {result}")
            return

        # Click on search bar
        print(f"\nClicking on search box at bbox: {result['bbox']}")
        click_rect(browser, result['bbox'], highlight=True, highlight_duration=1.0)
        time.sleep(0.5)

        # =================================================================
        # SCENE 2: Type Search Query
        # =================================================================
        print("\n[Scene 2] Typing search query: 'visiting japan'")
        browser.page.keyboard.type("visiting japan", delay=100)
        time.sleep(0.5)

        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene2_typing.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Press Enter
        print("Pressing Enter...")
        browser.page.keyboard.press("Enter")
        time.sleep(3)  # Wait for search results

        # =================================================================
        # SCENE 3: Select Non-Ad Search Result
        # =================================================================
        print("\n[Scene 3] Analyzing search results...")

        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene3_search_results.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Get snapshot using API (WASM extension issue fixed)
        print("Getting snapshot from API...")
        snap = snapshot(browser, screenshot=False, use_api=True)
        snapshot_data = snap.model_dump()
        print(f"API returned {len(snapshot_data.get('elements', []))} elements")

        # Save snapshot JSON
        with open(os.path.join(screenshots_dir, "sdk_scene3_data.json"), 'w') as f:
            json.dump(snapshot_data, f, indent=2)

        # Visualize elements with bounding boxes
        if snapshot_data.get('elements'):
            print("Visualizing elements with bounding boxes...")
            visualize_api_elements(screenshot_path, snapshot_data)

        # Scene 3 optimization: Keep only links and headings
        print("Applying Scene 3 element filtering...")
        filtered_data = filter_elements(snapshot_data, exclude_roles=[
            "searchbox", "combobox", "button", "img", "image",
            "span", "div", "svg", "path", "g", "rect", "circle",
            "ul", "li"
        ])

        # Additional filtering: remove ads by text content
        print("Filtering out ads by text content...")
        original_count = len(filtered_data.get('elements', []))
        non_ad_elements = [
            elem for elem in filtered_data.get('elements', [])
            if not any(ad_marker in elem.get('text', '').lower()
                      for ad_marker in ['ad', 'sponsored', '·'])
        ]
        filtered_data['elements'] = non_ad_elements
        print(f"  Ad filtering: {original_count} -> {len(non_ad_elements)} elements")

        # Ask LLM to select a result
        prompt = """You are an AI agent controlling a web browser.

Current Task: Select a non-ad search result link about "visiting japan".

Instructions:
1. Analyze the elements array (ads have already been filtered out)
2. Find result links (role="link") that are:
   - In viewport (in_viewport=true)
   - Not occluded (is_occluded=false)
   - Clickable (visual_cues.is_clickable=true)
   - Related to visiting Japan (tourism, travel guides, etc.)
3. Prefer high-quality sources (official tourism sites, reputable travel guides)
4. Select the first clearly visible, relevant result
5. Return the element ID and bbox coordinates

Response Format:
{
  "reasoning": "explanation of result selection",
  "result_title": "extracted from element text",
  "element_id": <id>,
  "bbox": {"x": <x>, "y": <y>, "width": <w>, "height": <h>},
  "action": "click"
}"""

        # Check if we have elements to analyze
        if not filtered_data.get('elements'):
            print("❌ ERROR: No search results found after filtering. Cannot proceed.")
            return

        result = agent.analyze_snapshot(filtered_data, prompt, "Scene 3: Select Search Result")

        # Validate result
        if not result.get('bbox') or result['bbox'].get('x') is None:
            print("❌ ERROR: LLM did not return valid coordinates")
            print(f"LLM response: {result}")
            return

        # Click on result
        print(f"\nClicking on result: {result.get('result_title', 'Unknown')}")
        print(f"Bbox: {result['bbox']}")

        # Get URL before click
        url_before = browser.page.url
        print(f"Current URL: {url_before}")

        click_rect(browser, result['bbox'], highlight=True, highlight_duration=1.0)
        time.sleep(3)  # Wait for navigation

        # Verify navigation
        url_after = browser.page.url
        print(f"After click URL: {url_after}")

        if url_before == url_after:
            print("⚠️  WARNING: URL did not change - click may have failed")
        else:
            print("✅ Successfully navigated to result page")

        # =================================================================
        # SCENE 4: Verify Success
        # =================================================================
        print("\n[Scene 4] Capturing final page...")

        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene4_result_page.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        print(f"\n✅ SUCCESS!")
        print(f"Final URL: {url_after}")

        time.sleep(2)

    # Print token usage summary
    tracker.print_summary()
    tracker.save_to_file(os.path.join(screenshots_dir, "token_summary.json"))

    print("\n" + "="*70)
    print("DEMO 1 COMPLETE!")
    print("="*70)
    print(f"Total tokens used: {tracker.total_tokens}")
    print(f"Screenshots saved to: {screenshots_dir}")

    # =================================================================
    # Generate Video
    # =================================================================
    print("\n" + "="*70)
    print("GENERATING DEMO VIDEO...")
    print("="*70)

    video_dir = os.path.join(os.path.dirname(__file__), 'video')
    os.makedirs(video_dir, exist_ok=True)
    video_output = os.path.join(video_dir, f"demo1_google_search_{timestamp}.mp4")

    try:
        create_demo_video(screenshots_dir, tracker.get_summary(), video_output)
        print(f"\n✅ Video generated successfully: {video_output}")
    except Exception as e:
        print(f"\n❌ Video generation failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
