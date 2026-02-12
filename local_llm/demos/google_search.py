"""
Google Search Demo using Local LLM
Simple test: Search for "visiting japan" and click first non-ad result
"""
import sys
import os
import time

# Add parent directories to path
demo_dir = os.path.dirname(__file__)
local_llm_dir = os.path.dirname(demo_dir)
playground_dir = os.path.dirname(local_llm_dir)
sys.path.insert(0, local_llm_dir)
sys.path.insert(0, playground_dir)

from predicate import PredicateBrowser, snapshot, click_rect
from models.local_llm import LocalLLM
from models.cloud_llm import CloudLLM
from shared.web_agent import WebAgent
from shared.utils import TimestampedFolder, ScreenshotManager, TokenTracker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def run_google_search_demo(
    llm_config: dict,
    search_query: str = "visiting japan",
    base_output_dir: str = None
):
    """
    Run Google search demo with specified LLM

    Args:
        llm_config: Dictionary with LLM configuration
            - For local: {"type": "local", "model_name": "Qwen/Qwen2.5-3B-Instruct", ...}
            - For cloud: {"type": "cloud", "model": "gpt-4-turbo-preview"}
        search_query: Search query to use
        base_output_dir: Base directory for outputs (default: playground/local_llm)

    Returns:
        Dictionary with results
    """
    # Determine output directory
    if base_output_dir is None:
        base_output_dir = local_llm_dir

    # Extract model name for demo identification
    if llm_config["type"] == "local":
        model_name = llm_config["model_name"].split("/")[-1]  # Get last part
        demo_name = f"google_search_{model_name}"
    else:
        demo_name = f"google_search_{llm_config['model']}"

    print(f"\n{'='*80}")
    print(f" "*25 + "GOOGLE SEARCH DEMO")
    print(f"{'='*80}")
    print(f"Demo: {demo_name}")
    print(f"Search query: '{search_query}'")
    print(f"{'='*80}\n")

    # Initialize LLM
    print("Initializing LLM...")
    if llm_config["type"] == "local":
        llm = LocalLLM(**{k: v for k, v in llm_config.items() if k != "type"})
    elif llm_config["type"] == "cloud":
        llm = CloudLLM(**{k: v for k, v in llm_config.items() if k != "type"})
    else:
        raise ValueError(f"Unknown LLM type: {llm_config['type']}")

    # Initialize utilities
    folder_manager = TimestampedFolder(base_output_dir, demo_name)
    token_tracker = TokenTracker(demo_name)
    agent = WebAgent(llm=llm, max_elements=50, verbose=True)  # Increased to capture search results deeper in DOM

    # Track timing
    start_time = time.time()
    results = {
        "demo_name": demo_name,
        "model": llm.model_name,
        "search_query": search_query,
        "scenes": []
    }

    try:
        with PredicateBrowser(headless=False) as browser:
            # ============================================================
            # SCENE 1: Navigate to Google & Find Search Box
            # ============================================================
            print(f"\n{'='*70}")
            print("SCENE 1: Find Google search box")
            print(f"{'='*70}")

            browser.goto("https://www.google.com")
            browser.page.wait_for_load_state("networkidle")
            time.sleep(2)  # Extra wait for page stability

            # Take screenshot
            screenshot_path = folder_manager.get_screenshot_path("scene1_homepage")
            ScreenshotManager.capture_and_save(browser, screenshot_path)

            # Get snapshot
            snapshot_obj = snapshot(browser, screenshot=False, use_api=True)
            snapshot_data = snapshot_obj.model_dump()  # Convert to dict
            folder_manager.save_json(snapshot_data, "scene1_homepage")

            # Find search box
            scene1_result = agent.analyze_and_select(
                snapshot_data=snapshot_data,
                task_type="find_input",
                context="Google search box"
            )

            if scene1_result is None:
                raise Exception("Failed to find search box")

            # Track tokens
            token_tracker.log_interaction(
                scene="Scene 1: Find search box",
                prompt_tokens=scene1_result["prompt_tokens"],
                completion_tokens=scene1_result["completion_tokens"],
                model_name=llm.model_name
            )

            # Click search box
            click_rect(browser, scene1_result["element"].bbox)
            time.sleep(0.5)

            results["scenes"].append({
                "name": "Scene 1: Find search box",
                "success": True,
                "tokens": scene1_result["tokens_used"],
                "element_id": scene1_result["id"],
                "reasoning": scene1_result["reasoning"]
            })

            # ============================================================
            # SCENE 2: Type Search Query
            # ============================================================
            print(f"\n{'='*70}")
            print(f"SCENE 2: Type search query '{search_query}'")
            print(f"{'='*70}")

            browser.page.keyboard.type(search_query, delay=100)
            time.sleep(0.3)
            browser.page.keyboard.press("Enter")
            browser.page.wait_for_load_state("networkidle")
            time.sleep(2)

            # Take screenshot
            screenshot_path = folder_manager.get_screenshot_path("scene2_search_results")
            ScreenshotManager.capture_and_save(browser, screenshot_path)

            results["scenes"].append({
                "name": "Scene 2: Type search query",
                "success": True,
                "tokens": 0,  # No LLM call
                "note": "Keyboard input only"
            })

            # ============================================================
            # SCENE 3: Select First Non-Ad Result
            # ============================================================
            print(f"\n{'='*70}")
            print("SCENE 3: Select first non-ad search result")
            print(f"{'='*70}")

            # Get snapshot
            snapshot_obj = snapshot(browser, screenshot=False, use_api=True)
            snapshot_data = snapshot_obj.model_dump()  # Convert to dict
            folder_manager.save_json(snapshot_data, "scene3_search_results")

            # Find first non-ad result
            scene3_result = agent.analyze_and_select(
                snapshot_data=snapshot_data,
                task_type="find_link",
                context="Select first organic (non-ad) search result",
                exclude_text_patterns=["Ad", "Sponsored", "·"]
            )

            if scene3_result is None:
                raise Exception("Failed to find search result - LLM could not identify a valid element")

            # Track tokens
            token_tracker.log_interaction(
                scene="Scene 3: Select search result",
                prompt_tokens=scene3_result["prompt_tokens"],
                completion_tokens=scene3_result["completion_tokens"],
                model_name=llm.model_name
            )

            # Click result
            click_rect(browser, scene3_result["element"].bbox, highlight=True)
            browser.page.wait_for_load_state("networkidle")
            time.sleep(3)

            # Take screenshot of target page
            screenshot_path = folder_manager.get_screenshot_path("scene4_target_page")
            ScreenshotManager.capture_and_save(browser, screenshot_path)

            final_url = browser.page.url
            print(f"\n✅ Navigated to: {final_url}")

            results["scenes"].append({
                "name": "Scene 3: Select search result",
                "success": True,
                "tokens": scene3_result["tokens_used"],
                "element_id": scene3_result["id"],
                "reasoning": scene3_result["reasoning"],
                "final_url": final_url
            })

            # ============================================================
            # DEMO COMPLETE
            # ============================================================
            print(f"\n{'='*80}")
            print(" "*30 + "DEMO COMPLETE!")
            print(f"{'='*80}")

            end_time = time.time()
            duration = end_time - start_time

            results["success"] = True
            results["duration_seconds"] = duration
            results["final_url"] = final_url

    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()

        results["success"] = False
        results["error"] = str(e)

    # Print token summary
    token_tracker.print_summary()

    # Save token summary
    token_summary_path = folder_manager.get_data_path("token_summary")
    token_tracker.save_to_file(token_summary_path)

    # Add token info to results
    results["token_summary"] = token_tracker.get_summary()

    # Save results
    results_path = folder_manager.get_data_path("results")
    folder_manager.save_json(results, "results")

    print(f"\n{'='*80}")
    print(f"Results saved to: {folder_manager.output_dir}")
    print(f"{'='*80}\n")

    return results


def main():
    """Run demo with default local LLM"""

    # Example: Run with Qwen 2.5 3B
    llm_config = {
        "type": "local",
        "model_name": "Qwen/Qwen2.5-3B-Instruct",
        "device": "auto",
        "load_in_4bit": False,  # Set to True if you have limited VRAM
    }

    results = run_google_search_demo(llm_config)

    if results["success"]:
        print("✅ Demo completed successfully!")
        print(f"   Total tokens: {results['token_summary']['total_tokens']}")
        print(f"   Duration: {results['duration_seconds']:.1f}s")
        print(f"   Final URL: {results.get('final_url', 'N/A')}")
    else:
        print(f"❌ Demo failed: {results.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
