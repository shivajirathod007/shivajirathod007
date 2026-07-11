import asyncio
import os
import re
import sys
import argparse
from playwright.async_api import async_playwright
try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None

# Selector helpers for TryHackMe page
JS_EXTRACT_STATS = r"""
() => {
  const stats = { rank: 'N/A', badges: 'N/A', streak: '0', completed: '0' };
  
  // Find card containers
  const divs = Array.from(document.querySelectorAll('div, section, a'));
  
  divs.forEach(el => {
    const text = el.innerText || '';
    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
    
    for (let i = 0; i < lines.length - 1; i++) {
      const line = lines[i];
      const val = lines[i+1];
      
      if (line === 'Rank' && (val.includes('Top') || /^\d+$/.test(val))) {
        stats.rank = val;
      } else if (line === 'Badges' && /^\d+$/.test(val)) {
        stats.badges = val;
      } else if (line === 'Streak' && /^\d+$/.test(val)) {
        stats.streak = val;
      } else if (line === 'Completed rooms' && /^\d+$/.test(val)) {
        stats.completed = val;
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
    if (rect.height < 150 || rect.width < 500) continue; // must be a large container card
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

def generate_gcp_svg(stats):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="120" viewBox="0 0 480 120" fill="none">
  <style>
    .title {{ font: 700 13px 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; fill: #4285F4; letter-spacing: 1px; }}
    .label {{ font: 500 10px 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; fill: #8b949e; letter-spacing: 0.5px; }}
    .value {{ font: 700 18px 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; fill: #e6edf3; }}
    .card {{ fill: #0d1117; stroke: #21262d; stroke-width: 1; rx: 6px; }}
    .divider {{ stroke: #21262d; stroke-width: 1; }}
  </style>
  <rect width="478" height="118" x="1" y="1" class="card"/>
  
  <!-- Header -->
  <path d="M20 22 L25 17 L30 22" stroke="#4285F4" stroke-width="2" fill="none" />
  <text x="35" y="21" class="title">GOOGLE CLOUD SKILLS BOOST STATUS</text>
  <line x1="20" y1="32" x2="460" y2="32" class="divider" />
  
  <!-- Stats columns -->
  <!-- Column 1: Member Since -->
  <text x="20" y="55" class="label">MEMBER SINCE</text>
  <text x="20" y="80" class="value">{stats.get('member_since', 'N/A')}</text>
  
  <!-- Column 2: League -->
  <text x="140" y="55" class="label">LEAGUE</text>
  <text x="140" y="80" class="value">{stats.get('league', 'N/A')} 💎</text>
  
  <!-- Column 3: Points -->
  <text x="280" y="55" class="label">POINTS</text>
  <text x="280" y="80" class="value">{stats.get('points', '0')}</text>
  
  <!-- Column 4: Badges -->
  <text x="380" y="55" class="label">BADGES</text>
  <text x="380" y="80" class="value">{stats.get('badges_count', '0')}</text>
</svg>
"""

async def run(username, dry_run=False):
    print(f"Starting TryHackMe scraping for user: {username}...")
    
    # Ensure assets dir exists
    if not dry_run:
        os.makedirs("assets", exist_ok=True)
        
    # Configure launch options for stealth & system browser execution
    chrome_path = "/usr/bin/google-chrome"
    launch_args = {
        "headless": False,  # Running headful is the most reliable way to bypass Cloudflare/Vercel
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox"
        ]
    }
    
    # Use Chrome channel on GitHub Actions (pre-installed), or local path
    if os.environ.get("GITHUB_ACTIONS") == "true":
        launch_args["channel"] = "chrome"
        print("Running on GitHub Actions: Using pre-installed Chrome channel")
    elif os.path.exists(chrome_path):
        launch_args["executable_path"] = chrome_path
        print(f"Using system Google Chrome at: {chrome_path}")

    # Use Stealth if available to wrap the playwright manager
    if Stealth:
        playwright_cm = Stealth().use_async(async_playwright())
        print("Stealth mode enabled for the browser session.")
    else:
        playwright_cm = async_playwright()

    async with playwright_cm as p:
        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Anti-bot bypass: remove the navigator.webdriver property
        await context.add_init_script("delete Object.getPrototypeOf(navigator).webdriver;")
        
        page = await context.new_page()
        
        # Set up response interceptors to capture TryHackMe API payloads passively
        profile_data = None
        rooms_data = None
        yearly_activity_data = None
        
        async def handle_response(response):
            nonlocal profile_data, rooms_data, yearly_activity_data
            url = response.url
            if "api/v2/public-profile?username=" in url:
                try:
                    profile_data = await response.json()
                    print("Intercepted public-profile API response!")
                except Exception as e:
                    print(f"Failed to parse public-profile JSON: {e}")
            elif "api/v2/public-profile/completed-rooms?username=" in url:
                try:
                    rooms_data = await response.json()
                    print("Intercepted completed-rooms API response!")
                except Exception as e:
                    print(f"Failed to parse completed-rooms JSON: {e}")
            elif "api/v2/public-profile/yearly-activity?username=" in url:
                try:
                    yearly_activity_data = await response.json()
                    print("Intercepted yearly-activity API response!")
                except Exception as e:
                    print(f"Failed to parse yearly-activity JSON: {e}")

        page.on("response", handle_response)
        
        # Load profile page first to initialize security/session bypass
        url_profile = f"https://tryhackme.com/p/{username}"
        print(f"Navigating to profile: {url_profile}")
        try:
            await page.goto(url_profile, wait_until="domcontentloaded", timeout=45000)
            # Wait up to 5 seconds for background API responses to be intercepted
            for _ in range(10):
                await page.wait_for_timeout(500)
                if profile_data and rooms_data:
                    break
        except Exception as e:
            print(f"Profile page navigation warning: {e}. Attempting to proceed...")

        # Process / Fetch profile statistics
        stats = {'rank': 'N/A', 'badges': 'N/A', 'streak': '0', 'completed': '0'}
        if profile_data and profile_data.get("status") == "success" and "data" in profile_data:
            print("Using intercepted profile statistics!")
            u_data = profile_data["data"]
            stats["rank"] = u_data.get("rank", "N/A")
            stats["badges"] = str(u_data.get("badgesNumber", "N/A"))
            stats["completed"] = str(u_data.get("completedRoomsNumber", "N/A"))
            stats["streak"] = str(u_data.get("streak", "0"))
        else:
            print("Fetching profile statistics from API fallback...")
            try:
                eval_data = await page.evaluate(
                    f"async () => {{ const r = await fetch('https://tryhackme.com/api/v2/public-profile?username={username}'); return await r.json(); }}"
                )
                if eval_data.get("status") == "success" and "data" in eval_data:
                    u_data = eval_data["data"]
                    stats["rank"] = u_data.get("rank", "N/A")
                    stats["badges"] = str(u_data.get("badgesNumber", "N/A"))
                    stats["completed"] = str(u_data.get("completedRoomsNumber", "N/A"))
                    stats["streak"] = str(u_data.get("streak", "0"))
                    print("Successfully fetched stats from API via page.evaluate!")
            except Exception as e:
                print(f"API stats fetch failed: {e}. Falling back to DOM parsing...")
                try:
                    stats = await page.evaluate(JS_EXTRACT_STATS)
                except Exception as dom_err:
                    print(f"DOM parsing fallback failed: {dom_err}")

        # Process / Fetch completed rooms
        top_rooms = []
        if rooms_data and rooms_data.get("status") == "success" and "data" in rooms_data:
            print("Using intercepted completed rooms!")
            docs = rooms_data["data"].get("docs", [])
            for doc in docs[:3]:
                top_rooms.append({
                    "name": doc.get("title", ""),
                    "link": f"https://tryhackme.com/room/{doc.get('code', '')}"
                })
        else:
            print("Fetching completed rooms list from API fallback...")
            try:
                eval_rooms = await page.evaluate(
                    f"async () => {{ const r = await fetch('https://tryhackme.com/api/v2/public-profile/completed-rooms?username={username}&limit=3&page=1'); return await r.json(); }}"
                )
                if eval_rooms.get("status") == "success" and "data" in eval_rooms:
                    docs = eval_rooms["data"].get("docs", [])
                    for doc in docs:
                        top_rooms.append({
                            "name": doc.get("title", ""),
                            "link": f"https://tryhackme.com/room/{doc.get('code', '')}"
                        })
                    print("Successfully fetched completed rooms from API via page.evaluate!")
            except Exception as e:
                print(f"API completed rooms fetch failed: {e}. Falling back to DOM parsing...")
                try:
                    rooms = []
                    room_elements = await page.locator("a[href*='/room/']").all()
                    for el in room_elements:
                        text = await el.inner_text()
                        href = await el.get_attribute("href")
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        if lines and href:
                            room_name = lines[0]
                            if room_name and room_name not in [r['name'] for r in rooms]:
                                full_href = f"https://tryhackme.com{href}" if href.startswith("/") else href
                                rooms.append({"name": room_name, "link": full_href})
                    top_rooms = rooms[:3]
                except Exception as dom_err:
                    print(f"DOM rooms parsing fallback failed: {dom_err}")
                
        print("Final Stats:", stats)
        print("Top 3 Completed Rooms:")
        for idx, r in enumerate(top_rooms):
            print(f" {idx+1}. {r['name']} ({r['link']})")
            
        # Navigate to Yearly Activity
        url_activity = f"https://tryhackme.com/p/{username}?tab=yearly-activity"
        print(f"Navigating to: {url_activity}")
        try:
            await page.goto(url_activity, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_selector("text=Yearly activity", timeout=25000)
            
            # Wait up to 10 seconds for yearly activity API response to be intercepted
            print("Waiting for yearly activity API response...")
            for _ in range(20):
                await page.wait_for_timeout(500)
                if yearly_activity_data:
                    break
            
            # Give heatmap additional time to render
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"Yearly activity page navigation warning: {e}. Attempting to proceed...")
            
        # Screenshot Yearly Activity heatmap
        print("Locating Yearly Activity heatmap container...")
        heatmap_handle = await page.evaluate_handle(JS_FIND_HEATMAP)
        heatmap_element = heatmap_handle.as_element()
        
        if heatmap_element:
            print("Found heatmap container. Capturing screenshot...")
            if not dry_run:
                await heatmap_element.scroll_into_view_if_needed()
                await page.wait_for_timeout(1500)
                await heatmap_element.screenshot(path="assets/thm-yearly-activity.png")
                print("Saved screenshot to assets/thm-yearly-activity.png")
            else:
                print("[Dry-run] Skipping heatmap screenshot save.")
        else:
            print("WARNING: Heatmap container not found! Taking fallback full-page screenshot.")
            if not dry_run:
                await page.screenshot(path="assets/thm-yearly-activity.png")
                
        # Fetch Google Cloud Skills Boost profile data
        url_gcp = "https://www.skills.google/public_profiles/85175627-c0be-4a34-9375-b21587ed7063"
        print(f"Navigating to Google Cloud Skills Boost: {url_gcp}")
        gcp_stats = {"member_since": "2025", "league": "N/A", "points": "0", "badges_count": "0"}
        try:
            await page.goto(url_gcp, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)
            gcp_text = await page.evaluate("document.body.innerText")
            
            # Extract GCP stats
            league_match = re.search(r'(Diamond|Gold|Silver|Bronze|Platinum)\s+League', gcp_text, re.IGNORECASE)
            if league_match:
                gcp_stats["league"] = league_match.group(0).split()[0]
                
            points_match = re.search(r'(\d+)\s+points', gcp_text, re.IGNORECASE)
            if points_match:
                gcp_stats["points"] = points_match.group(1)
                
            member_match = re.search(r'Member\s+since\s+(\d{4})', gcp_text, re.IGNORECASE)
            if member_match:
                gcp_stats["member_since"] = member_match.group(1)
                
            # Count badges
            badges_count = len(re.findall(r'Earned\s+', gcp_text, re.IGNORECASE))
            gcp_stats["badges_count"] = str(badges_count)
            print("Successfully fetched GCP stats:", gcp_stats)
        except Exception as e:
            print(f"Failed to fetch Google Cloud stats: {e}")
            
        await browser.close()
        
        # Write Stats SVG
        svg_content = generate_svg(stats)
        gcp_svg_content = generate_gcp_svg(gcp_stats)
        if not dry_run:
            with open("assets/thm-stats.svg", "w") as f:
                f.write(svg_content)
            print("Saved stats SVG to assets/thm-stats.svg")
            
            with open("assets/gcp-stats.svg", "w") as f:
                f.write(gcp_svg_content)
            print("Saved GCP stats SVG to assets/gcp-stats.svg")
        else:
            print("[Dry-run] Generated SVG Content:\n", svg_content)
            print("[Dry-run] Generated GCP SVG Content:\n", gcp_svg_content)
            
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
        
    stats_replacement = f"""<!-- thm-stats-start -->
<div align="center">
  <a href="https://tryhackme.com/p/hey.nexxum" target="_blank">
    <img src="assets/thm-stats.svg" alt="TryHackMe Stats" width="480" />
  </a>
</div>

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
