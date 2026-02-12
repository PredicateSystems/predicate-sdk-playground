# Amazon Best Sellers Shopping Guide - Predicate Python SDK

This guide demonstrates how to use the Predicate Python SDK to automate shopping on Amazon.

## Prerequisites
* install the `predicatelabs` sdk:
`pip install predicatelabs`

* install playwright with chromium support:
```bash
cd sdk-python
pip install -e .
playwright install chromium
```

## Complete Example: Amazon Best Sellers Shopping Bot

```python
"""
Amazon Best Sellers Shopping Bot
Navigate to Amazon, select a product, and add to cart
"""

from predicate import (
    PredicateBrowser,
    snapshot,
    find,
    click,
    screenshot,
    wait_for
)
import base64
import time


def save_screenshot(data_url: str, filename: str):
    """Helper function to save screenshot"""
    image_data = base64.b64decode(data_url.split(",")[1])
    with open(filename, "wb") as f:
        f.write(image_data)
    print(f"Screenshot saved: {filename}")


def main():
    # Initialize browser with custom viewport
    with PredicateBrowser(headless=False) as browser:
        print("Step 1: Navigating to Amazon Best Sellers...")

        # Navigate to Amazon Best Sellers page
        browser.goto("https://www.amazon.com/gp/bestsellers/?ref_=nav_cs_bestsellers")
        browser.page.wait_for_load_state("networkidle")
        time.sleep(2)  # Extra wait for dynamic content

        print("Step 2: Taking snapshot of the page...")

        # Take a snapshot with screenshot
        snap = snapshot(browser, screenshot=True) # take a screenshot of the browser

        # Save the snapshot screenshot
        if snap.screenshot:
            save_screenshot(snap.screenshot, "amazon_bestsellers.png")

        print(f"Found {len(snap.elements)} elements on the page")
        print(f"Current URL: {snap.url}")
        print(f"Viewport: {snap.viewport.width}x{snap.viewport.height}")

        # Inspect snapshot data structure
        print(f"\nSnapshot data structure:")
        print(f"  status: {snap.status}")
        print(f"  timestamp: {snap.timestamp}")
        print(f"  url: {snap.url}")
        print(f"  viewport: {snap.viewport}")
        print(f"  elements count: {len(snap.elements)}")
        print(f"  screenshot: {'present' if snap.screenshot else 'none'}")
        print(f"\nFirst 3 elements:")
        for i, el in enumerate(snap.elements[:3]):
            print(f"\n  Element {i}:")
            print(f"    id: {el.id}")
            print(f"    role: {el.role}")
            print(f"    text: {el.text}")
            print(f"    importance: {el.importance}")
            print(f"    bbox: x={el.bbox.x}, y={el.bbox.y}, w={el.bbox.width}, h={el.bbox.height}")
            print(f"    in_viewport: {el.in_viewport}")
            print(f"    is_occluded: {el.is_occluded}")
            print(f"    is_clickable: {el.visual_cues.is_clickable}")

        print("\nStep 3: Finding first product in the first row...")

        # Find clickable elements that might be products
        # Products are typically links with images
        # We'll look for links that are clickable and in the viewport
        products = []
        for element in snap.elements[:50]:  # Check first 50 elements
            if element.role == "link" and element.visual_cues.is_clickable:
                if element.in_viewport and not element.is_occluded:
                    # Check if it's in the top area (first row - y < 600 pixels)
                    if element.bbox.y < 600:
                        products.append(element)

        if not products:
            print("No products found in the first row!")
            return

        # Sort by position (left to right, top to bottom)
        products.sort(key=lambda e: (e.bbox.y, e.bbox.x))
        first_product = products[0]

        print(f"Found product element:")
        print(f"  - ID: {first_product.id}")
        print(f"  - Text: {first_product.text}")
        print(f"  - Position: ({first_product.bbox.x}, {first_product.bbox.y})")
        print(f"  - Importance: {first_product.importance}")

        print("\nStep 4: Clicking on the first product...")

        # Click the product
        result = click(browser, first_product.id)

        if not result.success:
            print(f"Failed to click: {result.error}")
            return

        print(f"Click successful! Outcome: {result.outcome}")

        # Wait for navigation
        browser.page.wait_for_load_state("networkidle")
        time.sleep(2)  # Extra wait for product page to fully load

        print(f"Navigated to: {browser.page.url}")

        print("\nStep 5: Looking for 'Add to Cart' button on product page...")

        # Take new snapshot on product details page
        product_snap = snapshot(browser, screenshot=True)

        if product_snap.screenshot:
            save_screenshot(product_snap.screenshot, "amazon_product_details.png")

        # Find "Add to Cart" button using multiple strategies
        add_to_cart = None

        # Strategy 1: Find by exact text match
        add_to_cart = find(product_snap, "role=button text='Add to Cart'")

        # Strategy 2: If not found, try case-insensitive substring match
        if not add_to_cart:
            add_to_cart = find(product_snap, "role=button text~'add to cart'")

        # Strategy 3: Look for any button with "cart" in the text
        if not add_to_cart:
            add_to_cart = find(product_snap, "role=button text~'cart'")

        if not add_to_cart:
            print("Could not find 'Add to Cart' button!")
            print("\nAvailable buttons on the page:")
            buttons = [el for el in product_snap.elements if el.role == "button"]
            for btn in buttons[:10]:  # Show first 10 buttons
                print(f"  - {btn.text}")
            return

        print(f"Found 'Add to Cart' button:")
        print(f"  - ID: {add_to_cart.id}")
        print(f"  - Text: {add_to_cart.text}")

        print("\nStep 6: Clicking 'Add to Cart' button...")

        # Click the Add to Cart button
        cart_result = click(browser, add_to_cart.id)

        if cart_result.success:
            print("Successfully added to cart!")
            print(f"Action outcome: {cart_result.outcome}")
        else:
            print(f"Failed to add to cart: {cart_result.error}")

        # Wait and take final screenshot
        time.sleep(2)
        final_screenshot = screenshot(browser, format="png")
        save_screenshot(final_screenshot, "amazon_after_add_to_cart.png")

        print("\nDone! Check the screenshots:")
        print("  1. amazon_bestsellers.png - Initial page")
        print("  2. amazon_product_details.png - Product page")
        print("  3. amazon_after_add_to_cart.png - After adding to cart")


if __name__ == "__main__":
    main()
```

## Step-by-Step Breakdown

### 1. Initialize Browser with Custom Viewport

```python
# Default viewport is 1280x800 (set in browser.py:117)
with PredicateBrowser(headless=False) as browser:
    # Browser starts with viewport 1280x800
    pass
```

**Answer to your viewport question:** Yes! You can specify viewport size when launching the browser. The viewport is configured in [browser.py:117](../sdk-python/sentience/browser.py#L117):

```python
self.context = self.playwright.chromium.launch_persistent_context(
    user_data_dir="",
    headless=False,
    args=args,
    viewport={"width": 1280, "height": 800},  # <-- Default viewport
    user_agent="..."
)
```

To customize the viewport, you would need to modify the `PredicateBrowser` class to accept viewport parameters:

```python
# Proposed modification (not yet implemented):
class PredicateBrowser:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        headless: Optional[bool] = None,
        viewport: Optional[dict] = None  # Add this parameter
    ):
        self.viewport = viewport or {"width": 1280, "height": 800}
        # ... rest of init

    def start(self) -> None:
        # ...
        self.context = self.playwright.chromium.launch_persistent_context(
            # ...
            viewport=self.viewport,  # Use custom viewport
            # ...
        )
```

### 2. Navigate to Amazon

```python
browser.goto("https://www.amazon.com/gp/bestsellers/?ref_=nav_cs_bestsellers")
browser.page.wait_for_load_state("networkidle")
```

The `goto()` method automatically:
- Navigates to the URL
- Waits for the extension to be ready
- Ensures the Sentience API is available

### 3. Take Snapshot with Screenshot

```python
snap = snapshot(browser, screenshot=True)

# Access snapshot data
print(f"URL: {snap.url}")
print(f"Viewport: {snap.viewport.width}x{snap.viewport.height}")
print(f"Elements: {len(snap.elements)}")

# Save screenshot if captured
if snap.screenshot:
    # snap.screenshot is a base64 data URL
    image_data = base64.b64decode(snap.screenshot.split(",")[1])
    with open("screenshot.png", "wb") as f:
        f.write(image_data)
```

#### Example Snapshot Data

Here's what the `snapshot()` function returns:

```python
# Snapshot object structure
{
    "status": "success",
    "timestamp": "2025-12-22T10:30:45.123Z",
    "url": "https://www.amazon.com/gp/bestsellers/",
    "viewport": {
        "width": 1280,
        "height": 800
    },
    "elements": [
        {
            "id": 1,
            "role": "link",
            "text": "Wireless Bluetooth Headphones - Noise Cancelling",
            "importance": 850,
            "bbox": {
                "x": 120.5,
                "y": 250.0,
                "width": 200.0,
                "height": 280.0
            },
            "visual_cues": {
                "is_primary": True,
                "background_color_name": "white",
                "is_clickable": True
            },
            "in_viewport": True,
            "is_occluded": False,
            "z_index": 1
        },
        {
            "id": 2,
            "role": "button",
            "text": "Add to Cart",
            "importance": 920,
            "bbox": {
                "x": 850.0,
                "y": 450.0,
                "width": 150.0,
                "height": 40.0
            },
            "visual_cues": {
                "is_primary": True,
                "background_color_name": "yellow",
                "is_clickable": True
            },
            "in_viewport": True,
            "is_occluded": False,
            "z_index": 2
        },
        {
            "id": 3,
            "role": "textbox",
            "text": None,
            "importance": 650,
            "bbox": {
                "x": 450.0,
                "y": 100.0,
                "width": 300.0,
                "height": 35.0
            },
            "visual_cues": {
                "is_primary": False,
                "background_color_name": None,
                "is_clickable": True
            },
            "in_viewport": True,
            "is_occluded": False,
            "z_index": 1
        }
        // ... more elements
    ],
    "screenshot": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "screenshot_format": "png",
    "error": None
}
```

**Accessing the data in Python:**

```python
snap = snapshot(browser, screenshot=True)

# Top-level properties
print(f"Status: {snap.status}")           # "success"
print(f"URL: {snap.url}")                  # "https://www.amazon.com/..."
print(f"Timestamp: {snap.timestamp}")      # "2025-12-22T10:30:45.123Z"

# Viewport
print(f"Viewport: {snap.viewport.width}x{snap.viewport.height}")  # "1280x800"

# Elements
print(f"Total elements: {len(snap.elements)}")  # e.g., 247

# Access individual elements
first_element = snap.elements[0]
print(f"Element ID: {first_element.id}")                    # 1
print(f"Role: {first_element.role}")                        # "link"
print(f"Text: {first_element.text}")                        # "Wireless Bluetooth..."
print(f"Importance: {first_element.importance}")            # 850
print(f"Position: ({first_element.bbox.x}, {first_element.bbox.y})")  # (120.5, 250.0)
print(f"Size: {first_element.bbox.width}x{first_element.bbox.height}") # 200.0x280.0
print(f"Clickable: {first_element.visual_cues.is_clickable}")  # True
print(f"In viewport: {first_element.in_viewport}")          # True
print(f"Occluded: {first_element.is_occluded}")             # False

# Screenshot (base64 data URL)
if snap.screenshot:
    print(f"Screenshot format: {snap.screenshot_format}")   # "png"
    print(f"Screenshot size: {len(snap.screenshot)} chars") # e.g., 125000
    # First 50 chars: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
```

**Example output when running the code:**

```
Step 2: Taking snapshot of the page...
Screenshot saved: amazon_bestsellers.png
Found 247 elements on the page
Current URL: https://www.amazon.com/gp/bestsellers/
Viewport: 1280x800

Snapshot data structure:
  status: success
  timestamp: 2025-12-22T10:30:45.123Z
  url: https://www.amazon.com/gp/bestsellers/
  viewport: Viewport(width=1280, height=800)
  elements count: 247
  screenshot: present

First 3 elements:
  Element 0:
    id: 1
    role: link
    text: Best Sellers in Electronics
    importance: 780
    bbox: x=45.0, y=120.0, w=180.0, h=24.0
    in_viewport: True
    is_occluded: False
    is_clickable: True

  Element 1:
    id: 2
    role: link
    text: Wireless Earbuds, Bluetooth 5.3 Headphones...
    importance: 850
    bbox: x=120.5, y=250.0, w=200.0, h=280.0
    in_viewport: True
    is_occluded: False
    is_clickable: True

  Element 2:
    id: 3
    role: button
    text: Add to List
    importance: 620
    bbox: x=340.0, y=460.0, w=100.0, h=32.0
    in_viewport: True
    is_occluded: False
    is_clickable: True
```

### 4. Find Product Using Element Selectors

There are multiple ways to find elements:

#### Method 1: Using Query DSL

```python
from predicate import find

# Find by role and text
product = find(snap, "role=link text~'Product Name'")

# Find clickable elements in viewport
product = find(snap, "clickable=true visible=true")

# Find by position (top-left area)
product = find(snap, "bbox.x<=100 bbox.y<=200")
```

#### Method 2: Manual Filtering

```python
# Find all products in first row (y < 600)
products = [
    el for el in snap.elements
    if el.role == "link"
    and el.visual_cues.is_clickable
    and el.in_viewport
    and not el.is_occluded
    and el.bbox.y < 600
]

# Sort by position (left to right, top to bottom)
products.sort(key=lambda e: (e.bbox.y, e.bbox.x))
first_product = products[0]
```

### 5. Click Element

```python
result = click(browser, element_id)

if result.success:
    print(f"Clicked successfully!")
    print(f"Outcome: {result.outcome}")  # "navigated", "dom_updated", etc.
    print(f"Duration: {result.duration_ms}ms")
    print(f"URL changed: {result.url_changed}")
else:
    print(f"Failed: {result.error}")
```

### 6. Find and Click "Add to Cart" Button

```python
# Take new snapshot on product page
product_snap = snapshot(browser)

# Try multiple strategies to find the button
add_to_cart = find(product_snap, "role=button text='Add to Cart'")

# Fallback: case-insensitive substring match
if not add_to_cart:
    add_to_cart = find(product_snap, "role=button text~'add to cart'")

# Click it
if add_to_cart:
    result = click(browser, add_to_cart.id)
```

## Query Selector Reference

The Predicate SDK uses a powerful query DSL. Here are the key operators:

### Basic Filters

```python
# Exact match
find(snap, "role=button")
find(snap, "text='Sign in'")

# Substring match (case-insensitive)
find(snap, "text~'add to cart'")

# Prefix match
find(snap, "text^='Add'")

# Suffix match
find(snap, "text$='Cart'")

# Exclusion
find(snap, "role!=link")
```

### Numeric Comparisons

```python
# Greater than / less than
find(snap, "importance>500")
find(snap, "bbox.y<600")

# Greater/less than or equal
find(snap, "importance>=100")
find(snap, "bbox.width<=300")
```

### Combined Filters

```python
# Multiple conditions (AND logic)
find(snap, "role=button text~'cart' clickable=true visible=true")
```

### Spatial Filters

```python
# Position
find(snap, "bbox.x<=100 bbox.y<=200")  # Top-left corner

# Size
find(snap, "bbox.width>=50 bbox.height>=30")

# Z-index (layering)
find(snap, "z_index>=100")
```

## API Reference

### Core Functions

- `PredicateBrowser(headless=False)` - Launch browser with extension
- `browser.goto(url)` - Navigate to URL
- `snapshot(browser, screenshot=True)` - Capture page state
- `screenshot(browser, format="png")` - Standalone screenshot
- `find(snapshot, selector)` - Find single element
- `click(browser, element_id)` - Click element
- `wait_for(browser, selector, timeout=5.0)` - Wait for element

### Element Properties

```python
element.id              # Unique identifier
element.role            # ARIA role (button, link, textbox, etc.)
element.text            # Visible text content
element.importance      # Importance score (0-1000)
element.bbox            # Bounding box (x, y, width, height)
element.visual_cues     # Visual analysis
element.in_viewport     # Is element visible in viewport?
element.is_occluded     # Is element covered by others?
element.z_index         # Stacking order
```

## Tips and Best Practices

1. **Wait for Dynamic Content**
   ```python
   browser.page.wait_for_load_state("networkidle")
   time.sleep(2)  # Extra wait for AJAX/animations
   ```

2. **Use Multiple Strategies for Finding Elements**
   ```python
   # Try exact match first
   btn = find(snap, "role=button text='Add to Cart'")
   # Fallback to fuzzy match
   if not btn:
       btn = find(snap, "role=button text~'cart'")
   ```

3. **Check Element Properties Before Clicking**
   ```python
   if element.in_viewport and not element.is_occluded:
       click(browser, element.id)
   ```

4. **Save Screenshots for Debugging**
   ```python
   snap = snapshot(browser, screenshot=True)
   if snap.screenshot:
       # Save for debugging
       save_screenshot(snap.screenshot, "debug.png")
   ```

5. **Handle Navigation Delays**
   ```python
   result = click(browser, element_id)
   if result.url_changed:
       browser.page.wait_for_load_state("networkidle")
   ```

## Viewport Configuration

Currently, the default viewport is **1280x800** pixels, set in [browser.py:117](../sdk-python/sentience/browser.py#L117).

To use a custom viewport size, you would need to modify the `PredicateBrowser` class:

```python
# Current implementation (simplified)
class PredicateBrowser:
    def start(self):
        self.context = self.playwright.chromium.launch_persistent_context(
            viewport={"width": 1280, "height": 800},  # Fixed size
            # ...
        )

# Proposed enhancement (not yet implemented)
class PredicateBrowser:
    def __init__(self, viewport_width=1280, viewport_height=800):
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

    def start(self):
        self.context = self.playwright.chromium.launch_persistent_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            # ...
        )
```

**Workaround:** You can resize the viewport after launch using Playwright's API:

```python
with PredicateBrowser(headless=False) as browser:
    # Set custom viewport size
    browser.page.set_viewport_size({"width": 1920, "height": 1080})

    # Now navigate
    browser.goto("https://www.amazon.com/...")
```

## Troubleshooting

### Issue: "Extension failed to load"

**Solution:** Make sure the extension is built:
```bash
cd sentience-chrome
./build.sh
```

### Issue: "Element not found"

**Solution:**
- Check if page is fully loaded: `browser.page.wait_for_load_state("networkidle")`
- Use `wait_for()` to wait for element: `wait_for(browser, "role=button", timeout=10)`
- Debug by listing all elements: `print([el.text for el in snap.elements])`

### Issue: Button not clickable

**Solution:**
- Check if element is in viewport: `element.in_viewport`
- Check if element is occluded: `element.is_occluded`
- Scroll to element: `browser.page.evaluate(f"window.sentience_registry[{element.id}].scrollIntoView()")`

## Further Reading

- [SDK README](../sdk-python/README.md) - Complete SDK documentation
- [Query DSL Guide](../sdk-python/docs/QUERY_DSL.md) - Advanced query patterns
- [Examples](../sdk-python/examples/) - More code examples
