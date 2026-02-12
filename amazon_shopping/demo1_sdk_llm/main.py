"""
Demo 1: Predicate SDK + LLM Agent for Amazon Shopping

This demo uses the SDK's snapshot() function to get structured JSON data,
then uses an LLM to analyze the data and make decisions.
"""
import os
import sys
import time
import json
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from predicate import PredicateBrowser, snapshot, click_rect, type_text, press
from llm_agent import LLMAgent
from token_tracker import TokenTracker
# Use simplified video generator (no ImageMagick/TextClip needed)
from video_generator_simple import create_demo_video
from bbox_visualizer import visualize_api_elements


def filter_elements(snapshot_data, exclude_roles):
    """
    Filter out elements with specific roles to reduce token usage

    Args:
        snapshot_data: The full snapshot data dictionary
        exclude_roles: List of role names to filter out (e.g., ["img", "button"])

    Returns:
        Filtered snapshot data with reduced elements array
    """
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
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    openai_api_key = os.getenv('OPENAI_API_KEY')
    predicate_api_key = os.getenv('PREDICATE_API_KEY')

    if not openai_api_key:
        print("ERROR: OPENAI_API_KEY not found in .env file")
        return

    # Initialize tracker and agent
    tracker = TokenTracker("Demo 1: SDK + LLM")
    agent = LLMAgent(api_key=openai_api_key, tracker=tracker)

    # Screenshot directory with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_screenshots_dir = os.path.join(os.path.dirname(__file__), 'screenshots')
    screenshots_dir = os.path.join(base_screenshots_dir, timestamp)
    os.makedirs(screenshots_dir, exist_ok=True)
    print(f"Screenshots will be saved to: {screenshots_dir}")

    print("\n" + "="*70)
    print("DEMO 1: Predicate SDK + LLM Agent - Amazon Shopping")
    print("="*70)

    with PredicateBrowser(api_key=predicate_api_key, headless=False) as browser:
        # Set viewport size (using 1600 height to allow panning in Scene 4)
        browser.page.set_viewport_size({"width": 1920, "height": 1080})

        # =================================================================
        # SCENE 1: Navigate to Amazon & Find Search Bar
        # =================================================================
        print("\n[Scene 1] Navigating to Amazon.com...")
        browser.page.goto("https://www.amazon.com", wait_until="domcontentloaded")
        time.sleep(3)  # Wait for page to fully load

        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene1_homepage.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Get snapshot (use local extension, not API)
        snap = snapshot(browser, screenshot=False, use_api=True)
        snapshot_data = snap.model_dump()

        # Save snapshot JSON
        with open(os.path.join(screenshots_dir, "sdk_scene1_data.json"), 'w') as f:
            json.dump(snapshot_data, f, indent=2)

        # Visualize API elements with bounding boxes
        print("Visualizing API-filtered elements...")
        visualize_api_elements(screenshot_path, snapshot_data)

        # Scene 1 optimization: Filter out img, button, link - we only need search input
        print("Applying Scene 1 element filtering...")
        filtered_data = filter_elements(snapshot_data, exclude_roles=["img", "button", "link"])

        # Ask LLM to find search bar
        prompt = """You are an AI agent controlling a web browser to shop on Amazon.

Current Task: Find the search bar on Amazon homepage.

Instructions:
1. Analyze the elements array
2. Find the search input field (likely role="textbox" or role="searchbox")
3. Look for elements with text like "Search" or empty text fields in top area (bbox.y < 200)
4. Prioritize elements that are in_viewport and not is_occluded
5. Return the element ID and bbox coordinates

Response Format:
{
  "reasoning": "brief explanation of why you selected this element",
  "element_id": <id>,
  "bbox": {"x": <x>, "y": <y>, "width": <w>, "height": <h>},
  "action": "click"
}"""

        result = agent.analyze_snapshot(filtered_data, prompt, "Scene 1: Find Search Bar")

        # Click on search bar
        print(f"\nClicking on search bar at bbox: {result['bbox']}")
        click_rect(browser, result['bbox'], highlight=True, highlight_duration=2.0)
        time.sleep(1)

        # =================================================================
        # SCENE 2: Type Search Query
        # =================================================================
        print("\n[Scene 2] Typing search query: 'Christmas gift'")
        browser.page.keyboard.type("Christmas gift", delay=100)
        time.sleep(0.5)

        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene2_typing.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Press Enter
        print("Pressing Enter...")
        browser.page.keyboard.press("Enter")
        time.sleep(4)  # Wait for search results

        # =================================================================
        # SCENE 3: Select Product from Search Results
        # =================================================================
        print("\n[Scene 3] Analyzing search results...")

        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene3_search_results.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Get snapshot (use local extension, not API)
        snap = snapshot(browser, screenshot=False, use_api=True)
        snapshot_data = snap.model_dump()

        # Save snapshot JSON
        with open(os.path.join(screenshots_dir, "sdk_scene3_data.json"), 'w') as f:
            json.dump(snapshot_data, f, indent=2)

        # Visualize API elements with bounding boxes
        print("Visualizing API-filtered elements...")
        visualize_api_elements(screenshot_path, snapshot_data)

        # Scene 3 optimization: Filter out searchbox, button - we only need product links
        print("Applying Scene 3 element filtering...")
        filtered_data = filter_elements(snapshot_data, exclude_roles=["searchbox", "button"])

        # Ask LLM to select a product
        prompt = """You are an AI agent controlling a web browser to shop on Amazon.

Current Task: Select a product from search results for "Christmas gift".

Instructions:
1. Analyze the elements array
2. Find product links (role="link") that are:
   - In viewport (in_viewport=true)
   - Not occluded (is_occluded=false)
   - Clickable (visual_cues.is_clickable=true)
   - In the main content area (bbox.y > 200, bbox.y < 900)
   - Have actual product text (not empty text)
3. Prefer products with higher importance scores
4. Select the first clearly visible product
5. Return the element ID and bbox coordinates

Response Format:
{
  "reasoning": "explanation of product selection",
  "product_title": "extracted from element text",
  "element_id": <id>,
  "bbox": {"x": <x>, "y": <y>, "width": <w>, "height": <h>},
  "action": "click"
}"""

        result = agent.analyze_snapshot(filtered_data, prompt, "Scene 3: Select Product")

        # Click on product
        print(f"\nClicking on product: {result.get('product_title', 'Unknown')}")
        print(f"Bbox: {result['bbox']}")
        click_rect(browser, result['bbox'], highlight=True, highlight_duration=2.0)
        # Wait for navigation (Amazon pages have continuous network activity, so use simple wait)
        print("Waiting for product page to load...")
        time.sleep(5)  # Simple wait - Amazon loads dynamically

        # =================================================================
        # SCENE 4: Find and Click "Add to Cart" Button
        # =================================================================
        print("\n[Scene 4] Finding 'Add to Cart' button...")

        # Take screenshot (viewport is already 1920x1600 for panning effect)
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene4_product_details.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Get snapshot (use local extension, not API)
        snap = snapshot(browser, screenshot=False, use_api=True)
        snapshot_data = snap.model_dump()

        # Save snapshot JSON
        with open(os.path.join(screenshots_dir, "sdk_scene4_data.json"), 'w') as f:
            json.dump(snapshot_data, f, indent=2)

        # Visualize API elements with bounding boxes
        print("Visualizing API-filtered elements...")
        visualize_api_elements(screenshot_path, snapshot_data)

        # Scene 4 optimization: Filter out searchbox, link - we only need buttons
        print("Applying Scene 4 element filtering...")
        filtered_data = filter_elements(snapshot_data, exclude_roles=["searchbox", "link"])

        # Ask LLM to find Add to Cart button
        prompt = """You are an AI agent controlling a web browser to shop on Amazon.

Current Task: Find and click the "Add to Cart" button on the product details page.

Instructions:
1. Analyze the elements array
2. Find the "Add to Cart" button:
   - role="button"
   - text contains "Add to Cart" (case-insensitive substring match)
   - In viewport and not occluded
   - Clickable (visual_cues.is_clickable=true)
3. Return the element ID and bbox coordinates

Response Format:
{
  "reasoning": "explanation of button identification",
  "button_text": "exact text from element",
  "element_id": <id>,
  "bbox": {"x": <x>, "y": <y>, "width": <w>, "height": <h>},
  "action": "click"
}"""

        result = agent.analyze_snapshot(filtered_data, prompt, "Scene 4: Add to Cart")

        # Click Add to Cart
        print(f"\nClicking 'Add to Cart' button: {result.get('button_text', 'Unknown')}")
        print(f"Bbox: {result['bbox']}")
        click_rect(browser, result['bbox'], highlight=True, highlight_duration=2.0)
        time.sleep(3)

        # =================================================================
        # SCENE 5: Verify Success
        # =================================================================
        print("\n[Scene 5] Verifying cart addition...")

        # Take screenshot
        screenshot_path = os.path.join(screenshots_dir, "sdk_scene5_confirmation.png")
        browser.page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Get snapshot (use local extension, not API)
        snap = snapshot(browser, screenshot=False, use_api=True)
        snapshot_data = snap.model_dump()

        # Save snapshot JSON
        with open(os.path.join(screenshots_dir, "sdk_scene5_data.json"), 'w') as f:
            json.dump(snapshot_data, f, indent=2)

        # Visualize API elements with bounding boxes
        print("Visualizing API-filtered elements...")
        visualize_api_elements(screenshot_path, snapshot_data)

        # Ask LLM to verify
        prompt = """You are an AI agent controlling a web browser to shop on Amazon.

Current Task: Verify that the item was successfully added to the cart.

Instructions:
1. Look for confirmation messages in the elements array:
   - Text containing "Added to Cart"
   - Text containing "Added to Shopping Cart"
   - Success-related text
2. Verify the action was successful

Response Format:
{
  "success": true/false,
  "reasoning": "explanation of verification",
  "confirmation_text": "text found that confirms addition or empty string if not found"
}"""

        result = agent.analyze_snapshot(snapshot_data, prompt, "Scene 5: Verify Success")

        if result.get('success'):
            print(f"\n✅ SUCCESS: {result.get('reasoning')}")
            print(f"Confirmation: {result.get('confirmation_text')}")
        else:
            print(f"\n❌ FAILED: {result.get('reasoning')}")

        time.sleep(2)

    # Print token usage summary
    tracker.print_summary()
    tracker.save_to_file(os.path.join(screenshots_dir, "token_summary.json"))

    # Generate video
    print("\n" + "="*70)
    print("Generating video with token overlay...")
    print("="*70)
    video_output = os.path.join(os.path.dirname(__file__), "video", "demo1_sdk_final.mp4")
    os.makedirs(os.path.dirname(video_output), exist_ok=True)

    try:
        create_demo_video(screenshots_dir, tracker.get_summary(), video_output)
    except Exception as e:
        print(f"Warning: Video generation failed: {e}")
        print("Screenshots and data are still available in the screenshots directory")

    print("\n" + "="*70)
    print("DEMO 1 COMPLETE!")
    print("="*70)


if __name__ == "__main__":
    main()
