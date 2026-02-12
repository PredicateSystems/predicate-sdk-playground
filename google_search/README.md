# Google Search Demo: SDK vs Vision

Simple test comparing Predicate SDK vs GPT-4o Vision for basic web automation.

## The Challenge

Complete a simple Google search:
1. Navigate to Google.com
2. Search for "visiting japan"
3. Click any non-ad result

## Structure

```
google_search/
├── demo1_sdk/              # SDK + LLM approach
│   ├── main.py             # Main demo script
│   └── screenshots/        # Timestamped screenshots + JSON
├── demo2_vision/           # Vision + LLM approach
│   ├── main.py             # Main demo script
│   └── screenshots/        # Timestamped screenshots + token data
├── shared/                 # Symlinks to shared utilities
│   ├── token_tracker.py
│   ├── llm_agent.py
│   ├── vision_agent.py
│   └── bbox_visualizer.py
├── run_demo1.sh            # Run SDK demo
├── run_demo2.sh            # Run Vision demo
└── README.md               # This file
```

## Running the Demos

### Prerequisites

1. Virtual environment with dependencies:
```bash
cd ../
source venv/bin/activate  # If using venv from amazon_shopping demos
```

2. Environment variables in `../.env`:
```
OPENAI_API_KEY=your_key_here
PREDICATE_API_KEY=your_key_here  # Only needed for demo1
```

### Run Demo 1 (SDK)

```bash
./run_demo1.sh
```

### Run Demo 2 (Vision)

```bash
./run_demo2.sh
```

## What Each Demo Does

### Demo 1: SDK Approach

1. **Scene 1**: Navigate to Google, find search box
   - Uses `snapshot()` to get structured JSON
   - Filters elements: excludes `["img", "button", "link"]`
   - LLM identifies searchbox from roles
   - Visualizes detected elements with colored bboxes

2. **Scene 2**: Type "visiting japan" and press Enter
   - No LLM call (simple keyboard input)

3. **Scene 3**: Select non-ad result
   - Uses `snapshot()` to get search results
   - Filters elements: excludes `["searchbox", "button", "img"]`
   - Filters out ads by text ("Ad", "Sponsored", "·")
   - LLM selects relevant, high-quality result
   - Visualizes results with annotations

4. **Scene 4**: Verify navigation
   - Takes screenshot of result page
   - Confirms URL changed

### Demo 2: Vision Approach

1. **Scene 1**: Navigate to Google, find search box
   - Takes screenshot
   - GPT-4o Vision identifies search box coordinates
   - Clicks coordinates

2. **Scene 2**: Type "visiting japan" and press Enter
   - No LLM call (simple keyboard input)

3. **Scene 3**: Select non-ad result
   - Takes screenshot of search results
   - GPT-4o Vision must visually identify non-ad results
   - Returns coordinates to click
   - Includes retry logic if navigation fails

4. **Scene 4**: Verify navigation
   - Takes screenshot of result page
   - Confirms URL changed

## Expected Results

Based on the plan:

| Metric | Demo 1 (SDK) | Demo 2 (Vision) |
|--------|--------------|-----------------|
| **Token Usage** | ~2,000-3,300 | ~3,700-5,000 |
| **Success Rate** | High (95%+) | Medium (70-85%) |
| **Ad Avoidance** | High (can filter by text) | Lower (visual detection) |
| **Runtime** | ~30-40s | ~30-40s |

### Key Advantages of SDK Approach

1. **Ad Filtering**: Can exclude ads by text content before LLM sees them
2. **Element Filtering**: Reduces tokens by 40-50% through role-based filtering
3. **Semantic Understanding**: Knows what's a button vs link vs searchbox
4. **Precise Targeting**: Bounding boxes are guaranteed correct
5. **Debugging**: Color-coded bbox visualizations show what API detected

### Key Challenges for Vision Approach

1. **Ad Detection**: Must visually identify "Ad"/"Sponsored" labels
2. **Token Cost**: Full screenshots use more tokens
3. **Coordinate Precision**: Clicking exact right spot on a link
4. **No Semantic Info**: Can't tell element types from pixels

## Output

Each demo creates a timestamped folder with:
- Screenshots of each scene
- Token usage summary JSON
- (Demo 1 only) Annotated screenshots with colored bounding boxes
- (Demo 1 only) Snapshot JSON data from API

### Demo 1 Output Example:
```
demo1_sdk/screenshots/20241222_180000/
├── sdk_scene1_google_home.png
├── sdk_scene1_google_home_annotated.png  # With bboxes!
├── sdk_scene1_data.json
├── sdk_scene2_typing.png
├── sdk_scene3_search_results.png
├── sdk_scene3_search_results_annotated.png
├── sdk_scene3_data.json
├── sdk_scene4_result_page.png
└── token_summary.json
```

### Demo 2 Output Example:
```
demo2_vision/screenshots/20241222_180030/
├── vision_scene1_google_home.png
├── vision_scene2_typing.png
├── vision_scene3_search_results.png
├── vision_scene4_result_page.png
└── token_summary.json
```

## Comparing Results

After running both demos, compare:

1. **Token usage**: Check `token_summary.json` in each timestamped folder
2. **Success rate**: Did both reach the final page?
3. **Ad avoidance**: Check final URLs - did either click an ad?
4. **Quality**: Which demo selected a better/more relevant result?

## Troubleshooting

**Demo 1 Issues**:
- "API key not found": Set `PREDICATE_API_KEY` in `../.env`
- "No elements found": Google layout may have changed, check annotated screenshots

**Demo 2 Issues**:
- "Refusal from Vision API": Prompts may need adjustment for content policy
- "Navigation failed": Vision model may have clicked wrong coordinates
- "Could not find search box": Vision model confused by page layout

**Both Demos**:
- "OPENAI_API_KEY not found": Set it in `../.env`
- Browser crashes: Check Playwright installation (`pip install playwright && playwright install`)

## Next Steps

1. Run both demos 3 times each
2. Compare average token usage
3. Calculate success rates
4. Document which sites were clicked
5. Create comparison report in `docs/GOOGLE_SEARCH_COMPARISON.md`

---

*See `docs/GOOGLE_SEARCH_DEMO_PLAN.md` for full plan and methodology*
