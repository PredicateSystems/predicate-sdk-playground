"""
Test script to verify local LLM setup
"""
import sys
import os

# Add to path
local_llm_dir = os.path.dirname(__file__)
sys.path.insert(0, local_llm_dir)


def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")

    try:
        from models.base_llm import BaseLLM, LLMResponse
        print("  ✅ base_llm")
    except ImportError as e:
        print(f"  ❌ base_llm: {e}")
        return False

    try:
        from models.local_llm import LocalLLM
        print("  ✅ local_llm")
    except ImportError as e:
        print(f"  ❌ local_llm: {e}")
        return False

    try:
        from models.cloud_llm import CloudLLM
        print("  ✅ cloud_llm")
    except ImportError as e:
        print(f"  ❌ cloud_llm: {e}")
        return False

    try:
        from shared.utils import TokenTracker, TimestampedFolder, ScreenshotManager
        print("  ✅ utils")
    except ImportError as e:
        print(f"  ❌ utils: {e}")
        return False

    try:
        from shared.element_processor import ElementFilter, ElementSnapshot, RawElement
        print("  ✅ element_processor")
    except ImportError as e:
        print(f"  ❌ element_processor: {e}")
        return False

    try:
        from shared.prompt_builder import PromptBuilder
        print("  ✅ prompt_builder")
    except ImportError as e:
        print(f"  ❌ prompt_builder: {e}")
        return False

    try:
        from shared.response_parser import ResponseParser
        print("  ✅ response_parser")
    except ImportError as e:
        print(f"  ❌ response_parser: {e}")
        return False

    try:
        from shared.web_agent import WebAgent
        print("  ✅ web_agent")
    except ImportError as e:
        print(f"  ❌ web_agent: {e}")
        return False

    return True


def test_dependencies():
    """Test that required dependencies are installed"""
    print("\nTesting dependencies...")

    dependencies = [
        ("sentience", "Predicate SDK"),
        ("transformers", "Hugging Face Transformers"),
        ("torch", "PyTorch"),
        ("openai", "OpenAI"),
        ("dotenv", "Python-dotenv"),
    ]

    all_found = True
    for module, name in dependencies:
        try:
            __import__(module)
            print(f"  ✅ {name}")
        except ImportError:
            print(f"  ❌ {name} - Run: pip install {module}")
            all_found = False

    # Optional dependencies
    optional_deps = [
        ("bitsandbytes", "BitsAndBytes (for quantization)"),
        ("accelerate", "Accelerate (for GPU acceleration)"),
        ("optimum", "Optimum (for faster inference)"),
    ]

    print("\nOptional dependencies:")
    for module, name in optional_deps:
        try:
            __import__(module)
            print(f"  ✅ {name}")
        except ImportError:
            print(f"  ⚠️  {name} - Optional but recommended")

    return all_found


def test_prompt_builder():
    """Test prompt builder"""
    print("\nTesting prompt builder...")

    from shared.prompt_builder import PromptBuilder

    # Mock compressed elements
    compressed_elements = {
        "elements": [
            {
                "id": 1,
                "role": "textbox",
                "text": "Search",
                "bbox": {"x": 100, "y": 50, "w": 600, "h": 40},
                "clickable": True,
                "visible": True,
                "score": 0.95
            },
            {
                "id": 2,
                "role": "button",
                "text": "Google Search",
                "bbox": {"x": 720, "y": 50, "w": 120, "h": 40},
                "clickable": True,
                "visible": True,
                "score": 0.85
            }
        ],
        "count": 2
    }

    try:
        prompt = PromptBuilder.build_task_prompt(
            task_type="find_input",
            compressed_elements=compressed_elements,
            additional_context="search box"
        )

        assert "search box" in prompt.lower()
        assert "textbox" in prompt.lower()
        print("  ✅ Prompt builder working")
        return True

    except Exception as e:
        print(f"  ❌ Prompt builder failed: {e}")
        return False


def test_response_parser():
    """Test response parser"""
    print("\nTesting response parser...")

    from shared.response_parser import ResponseParser

    # Test JSON extraction
    test_cases = [
        ('{"id": 42, "reasoning": "test"}', 42),
        ('```json\n{"id": 42, "reasoning": "test"}\n```', 42),
        ('Some text\n{"id": 42, "reasoning": "test"}\nMore text', 42),
    ]

    all_passed = True
    for response, expected_id in test_cases:
        parsed = ResponseParser.extract_json(response)
        if parsed and parsed.get("id") == expected_id:
            print(f"  ✅ Parsed: {response[:50]}...")
        else:
            print(f"  ❌ Failed to parse: {response[:50]}...")
            all_passed = False

    return all_passed


def main():
    """Run all tests"""
    print(f"\n{'='*70}")
    print(" "*20 + "LOCAL LLM SETUP TEST")
    print(f"{'='*70}\n")

    results = []

    # Test imports
    results.append(("Imports", test_imports()))

    # Test dependencies
    results.append(("Dependencies", test_dependencies()))

    # Test components
    results.append(("Prompt Builder", test_prompt_builder()))
    results.append(("Response Parser", test_response_parser()))

    # Summary
    print(f"\n{'='*70}")
    print(" "*25 + "TEST SUMMARY")
    print(f"{'='*70}")

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:30} {status}")

    all_passed = all(passed for _, passed in results)

    print(f"{'='*70}\n")

    if all_passed:
        print("✅ All tests passed! Setup is ready.")
        print("\nNext steps:")
        print("1. Download a model:")
        print("   python -c \"from transformers import AutoTokenizer, AutoModelForCausalLM; AutoTokenizer.from_pretrained('Qwen/Qwen2.5-3B-Instruct'); AutoModelForCausalLM.from_pretrained('Qwen/Qwen2.5-3B-Instruct')\"")
        print("\n2. Run the demo:")
        print("   python demos/google_search.py")
    else:
        print("❌ Some tests failed. Please install missing dependencies.")
        print("\nInstall command:")
        print("   pip install -r requirements.txt")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
