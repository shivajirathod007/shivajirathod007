import asyncio
import os
import re
import sys
import argparse
from playwright.async_api import async_playwright

# Selector helpers for TryHackMe page
JS_EXTRACT_STATS = """
() => {
  const stats = { rank: 'N/A', badges: 'N/A', streak: '0', completed: '0' };
  
  // Find card containers
  const divs = Array.from(document.querySelectorAll('div, section, a'));
  
  divs.forEach(el => {
    const text = el.innerText || '';
    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line === 'Rank' && i + 1 < lines.length) {
        stats.rank = lines[i+1];
      } else if (line === 'Badges' && i + 1 < lines.length) {
        stats.badges = lines[i+1];
      } else if (line === 'Streak' && i + 1 < lines.length) {
        stats.streak = lines[i+1];
      } else if (line === 'Completed rooms' && i + 1 < lines.length) {
        stats.completed = lines[i+1];
      }
    }
  });
  
  return stats;
}
"""

JS_FIND_HEATMAP = """
() => {
  const divs = Array.from(document.querySelectorAll('div'));
  let best = null;
  let minArea = Infinity;
  for (const div of divs) {
    const rect = div.getBoundingClientRect();
    const area = rect.width * rect.height;
    if (area < 10000) continue; // too small to be the heatmap card
    const text = div.innerText || '';
    if (text.includes('Yearly activity') && (div.querySelector('svg') || div.querySelectorAll('*').length > 50)) {
      if (area < minArea) {
        minArea = area;
        best = div;
      }
    }
  }
  return best;
}
"""

def generate_svg(stats):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="120" viewBox="0 0 480 120" fill="none">
  <style>
    .title {{ font: 700 13px 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; fill: #3fb950; letter-spacing: 1px; }}
    .label {{ font: 500 10px 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; fill: #8b949e; letter-spacing: 0.5px; }}
    .value {{ font: 700 18px 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; fill: #e6edf3; }}
    .card {{ fill: #0d1117; stroke: #21262d; stroke-width: 1; rx: 6px; }}
    .divider {{ stroke: #21262d; stroke-width: 1; }}
  </style>
  <rect width="478" height="118" x="1" y="1" class="card"/>
  
  <!-- Header -->
  <path d="M20 22 L25 17 L30 22" stroke="#3fb950" stroke-width="2" fill="none" />
  <text x="35" y="21" class="title">TRYHACKME PROFILE STATUS</text>
  <line x1="20" y1="32" x2="460" y2="32" class="divider" />
  
  <!-- Stats columns -->
  <!-- Column 1: Rank -->
  <text x="20" y="55" class="label">RANK</text>
  <text x="20" y="80" class="value">{stats.get('rank', 'N/A')}</text>
  
  <!-- Column 2: Completed -->
  <text x="130" y="55" class="label">COMPLETED ROOMS</text>
  <text x="130" y="80" class="value">{stats.get('completed', 'N/A')}</text>
  
  <!-- Column 3: Badges -->
  <text x="280" y="55" class="label">BADGES</text>
  <text x="280" y="80" class="value">{stats.get('badges', 'N/A')}</text>
  
  <!-- Column 4: Streak -->
  <text x="380" y="55" class="label">STREAK</text>
  <text x="380" y="80" class="value">{stats.get('streak', 'N/A')} 🔥</text>
</svg>
"""

async def run(username, dry_run=False):
    print(f"Starting TryHackMe scraping for user: {username}...")
    
    # Ensure assets dir exists
    if not dry_run:
        os.makedirs("assets", exist_ok=True)
        
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Load Completed Rooms page
        url_completed = f"https://tryhackme.com/p/{username}?tab=completed-rooms"
        print(f"Navigating to: {url_completed}")
        await page.goto(url_completed, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000) # extra wait for dynamic JS content
        
        # Extract profile stats
        print("Extracting profile statistics...")
        stats = await page.evaluate(JS_EXTRACT_STATS)
        
        # If JS extraction was incomplete, try fallback regex on page text
        page_text = await page.evaluate("document.body.innerText")
        
        if stats.get('rank') == 'N/A':
            rank_match = re.search(r'Rank\s+(Top\s+\d+%)', page_text, re.IGNORECASE)
            if rank_match:
                stats['rank'] = rank_match.group(1)
            else:
                rank_match = re.search(r'(Top\s+\d+%)\s+Rank', page_text, re.IGNORECASE)
                if rank_match:
                    stats['rank'] = rank_match.group(1)
                    
        if stats.get('badges') == 'N/A':
            badges_match = re.search(r'Badges\s+(\d+)', page_text, re.IGNORECASE)
            if badges_match:
                stats['badges'] = badges_match.group(1)
                
        if stats.get('streak') == '0':
            streak_match = re.search(r'Streak\s+(\d+)', page_text, re.IGNORECASE)
            if streak_match:
                stats['streak'] = streak_match.group(1)
                
        if stats.get('completed') == '0':
            completed_match = re.search(r'Completed rooms\s+(\d+)', page_text, re.IGNORECASE)
            if completed_match:
                stats['completed'] = completed_match.group(1)
        
        print("Extracted Stats:", stats)
        
        # Extract room names and links
        print("Extracting completed rooms list...")
        rooms = []
        room_elements = await page.locator("a[href*='/room/']").all()
        for el in room_elements:
            text = await el.inner_text()
            href = await el.get_attribute("href")
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if lines and href:
                room_name = lines[0]
                # Avoid non-room strings or duplicates
                if room_name and room_name not in [r['name'] for r in rooms]:
                    full_href = f"https://tryhackme.com{href}" if href.startswith("/") else href
                    rooms.append({
                        "name": room_name,
                        "link": full_href
                    })
                    
        top_rooms = rooms[:3]
        print("Top 3 Completed Rooms:")
        for idx, r in enumerate(top_rooms):
            print(f" {idx+1}. {r['name']} ({r['link']})")
            
        # Navigate to Yearly Activity
        url_activity = f"https://tryhackme.com/p/{username}?tab=yearly-activity"
        print(f"Navigating to: {url_activity}")
        await page.goto(url_activity, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        
        # Screenshot Yearly Activity heatmap
        print("Locating Yearly Activity heatmap container...")
        heatmap_handle = await page.evaluate_handle(JS_FIND_HEATMAP)
        heatmap_element = heatmap_handle.as_element()
        
        if heatmap_element:
            print("Found heatmap container. Capturing screenshot...")
            if not dry_run:
                # Scroll to it
                await heatmap_element.scroll_into_view_if_needed()
                await page.wait_for_timeout(1000)
                await heatmap_element.screenshot(path="assets/thm-yearly-activity.png")
                print("Saved screenshot to assets/thm-yearly-activity.png")
            else:
                print("[Dry-run] Skipping heatmap screenshot save.")
        else:
            print("WARNING: Heatmap container not found! Taking fallback full-page screenshot.")
            if not dry_run:
                await page.screenshot(path="assets/thm-yearly-activity.png")
                
        await browser.close()
        
        # Write Stats SVG
        svg_content = generate_svg(stats)
        if not dry_run:
            with open("assets/thm-stats.svg", "w") as f:
                f.write(svg_content)
            print("Saved stats SVG to assets/thm-stats.svg")
        else:
            print("[Dry-run] Generated SVG Content:\n", svg_content)
            
        # Update README
        if not dry_run:
            update_readme(top_rooms)
            
def update_readme(top_rooms):
    readme_path = "README.md"
    if not os.path.exists(readme_path):
        print(f"Error: {readme_path} not found.")
        return
        
    with open(readme_path, "r") as f:
        readme_content = f.read()
        
    # Generate the replacement block
    rooms_table_rows = ""
    for r in top_rooms:
        rooms_table_rows += f"| **{r['name']}** | [Room Link]({r['link']}) |\n"
        
    if not rooms_table_rows:
        rooms_table_rows = "| *No recent rooms found* | - |\n"
        
    stats_replacement = f"""<!-- thm-stats-start -->
<div align="center">
  <img src="assets/thm-stats.svg" alt="TryHackMe Stats" width="480" />
</div>

<br/>

#### ⬡ Recent Completed Rooms
| Room Name | Link |
| :--- | :--- |
{rooms_table_rows}
<br/>

#### ⬡ TryHackMe Yearly Activity
<div align="center">
  <a href="https://tryhackme.com/p/hey.nexxum?tab=yearly-activity" target="_blank">
    <img src="assets/thm-yearly-activity.png" alt="TryHackMe Yearly Activity" width="100%" style="border-radius: 6px; border: 1px solid #30363d;" />
  </a>
</div>
<!-- thm-stats-end -->"""

    # Replace block between comments
    pattern = r"<!-- thm-stats-start -->.*?<!-- thm-stats-end -->"
    if re.search(pattern, readme_content, re.DOTALL):
        updated_content = re.sub(pattern, stats_replacement, readme_content, flags=re.DOTALL)
        with open(readme_path, "w") as f:
            f.write(updated_content)
        print("Updated README.md with TryHackMe stats.")
    else:
        print("WARNING: Could not find <!-- thm-stats-start --> and <!-- thm-stats-end --> placeholders in README.md.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape TryHackMe stats and update README.")
    parser.add_argument("--username", default="hey.nexxum", help="TryHackMe username to scrape.")
    parser.add_argument("--dry-run", action="store_true", help="Print stats instead of writing files.")
    args = parser.parse_args()
    
    asyncio.run(run(args.username, args.dry_run))
