import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone

def scrape_data():
    print("Starting scraper for raids, max battles, and events...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    final_data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "raids": [],
        "max_battles": [],
        "events": []
    }

    # --- 1. LEEKDUCK RAIDS ---
    try:
        ld_response = requests.get("https://leekduck.com/raid-bosses/", headers=headers)
        ld_soup = BeautifulSoup(ld_response.text, 'html.parser')
        
        for raid_container in ld_soup.find_all('div', class_=['raid-bosses', 'shadow-raid-bosses']):
            for tier_group in raid_container.find_all('div', class_='tier'):
                tier_name = tier_group.find('h2').get('data-tier', 'Unknown')
                
                for card in tier_group.find_all('div', class_='card'):
                    name = card.find('p', class_='name').text.strip()
                    img_tag = card.find('div', class_='boss-img').find('img')
                    img_url = img_tag['src'] if img_tag else ""
                    if img_url and not img_url.startswith('http'):
                        img_url = f"https://leekduck.com{img_url}"
                        
                    final_data["raids"].append({
                        "name": name,
                        "tier": tier_name,
                        "is_shadow": 'shadow-raid-bosses' in raid_container.get('class', [])
                    })
        print(f"Successfully loaded {len(final_data['raids'])} raids.")
    except Exception as e:
        print(f"Error scraping raids: {e}")

    # --- 2. MINPOKE MAX BATTLES ---
    try:
        mp_response = requests.get("https://9db.jp/pokemongo/data/20859", headers=headers)
        mp_soup = BeautifulSoup(mp_response.text, 'html.parser')
        
        current_tab = mp_soup.find('div', id='wiki_tab0')
        if current_tab:
            current_level = 1
            
            for element in current_tab.find_all(['table', 'p']):
                
                if element.name == 'table' and 'wiki_noborder' in element.get('class', []):
                    icons = element.find_all('img', src=lambda s: s and 'w_boss.png' in s)
                    if len(icons) > 0:
                        current_level = len(icons)
                
                elif element.name == 'p':
                    for boss_span in element.find_all('span', class_='wiki_tier_boss'):
                        name_span = boss_span.find_all('span', recursive=False)[-1]
                        name = name_span.text.strip()
                        
                        img_tag = boss_span.find('img', class_='wiki_dmax')
                        img_url = img_tag['src'] if img_tag else ""
                        
                        final_data["max_battles"].append({
                            "name_jp": name,
                            "level": f"tier_{current_level}",
                        })
        print(f"Successfully loaded {len(final_data['max_battles'])} max battles.")
    except Exception as e:
        print(f"Error scraping max battles: {e}")

    # --- 3. LEEKDUCK EVENTS & SCHEDULED BOSSES ---
    try:
        ev_response = requests.get("https://leekduck.com/events/", headers=headers)
        ev_soup = BeautifulSoup(ev_response.text, 'html.parser')
        
        events_dict = {}
        
        for item in ev_soup.find_all('span', class_='event-header-item-wrapper'):
            title_tag = item.find('h2')
            if not title_tag:
                continue
                
            title = title_tag.text.strip()
            event_type = item.get('data-event-type', 'event')
            start_date = item.get('data-event-start-date') or item.get('data-event-start-date-check')
            end_date = item.get('data-event-end-date') or item.get('data-event-date-sort')
            is_local = item.get('data-event-local-time') == 'true'

            link_tag = item.find('a', class_='event-item-link')
            link = f"https://leekduck.com{link_tag['href']}" if link_tag and 'href' in link_tag.attrs else ""

            if title not in events_dict:
                events_dict[title] = {
                    "title": title,
                    "type": event_type,
                    "start": start_date,
                    "end": end_date,
                    "is_local_time": is_local,
                    "link": link
                }
            else:
                if item.get('data-event-start-date') and not events_dict[title].get('start'):
                    events_dict[title]['start'] = item.get('data-event-start-date')
                if item.get('data-event-end-date'):
                    events_dict[title]['end'] = item.get('data-event-end-date')

        final_data["events"] = list(events_dict.values())
        final_data["scheduled_bosses"] = []
        seen_scheduled = set()

        for ev in final_data["events"]:
            title = ev["title"]
            event_type = ev["type"]
            start_date = ev["start"]
            end_date = ev["end"]
            link = ev.get("link", "")

            if not start_date or not end_date or start_date == end_date:
                continue

            # A) Klassische "Boss in 5-star/Mega/Shadow Raids" Einträge (nach dem Merge!)
            if event_type == 'raid-battles' and " in " in title:
                boss_name_raw = title.split(" in ")[0].strip()
                tier = "Unknown"
                if "5-star" in title or "5-Star" in title:
                    tier = "5-star"
                elif "Mega" in title:
                    tier = "Mega"
                elif "Shadow" in title:
                    tier = "Shadow"

                key = (boss_name_raw.lower(), tier, start_date, end_date)
                if key not in seen_scheduled:
                    seen_scheduled.add(key)
                    final_data["scheduled_bosses"].append({
                        "name": boss_name_raw,
                        "tier": tier,
                        "start": start_date,
                        "end": end_date,
                    })

            # B) Event-Unterseiten (z.B. "Into the Wild 2026") nach 5-Star / Mega Raids durchsuchen
            elif event_type in ('event', 'wild-area', 'raid-day', 'pokémon-go-tour', 'go-fest') and link:
                try:
                    detail_resp = requests.get(link, headers=headers, timeout=10)
                    detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                    for h3 in detail_soup.find_all(['h2', 'h3', 'h4']):
                        heading_text = h3.get_text(" ", strip=True).lower()
                        tier = None
                        if '5-star' in heading_text or 'five-star' in heading_text:
                            tier = '5-star'
                        elif 'mega raid' in heading_text:
                            tier = 'Mega'
                        elif 'shadow raid' in heading_text and '5' in heading_text:
                            tier = 'Shadow'
                        if not tier:
                            continue

                        ul = h3.find_next_sibling('ul', class_='pkmn-list-flex')
                        if not ul:
                            continue
                        for pkmn_li in ul.find_all('li', class_='pkmn-list-item'):
                            name_div = pkmn_li.find(class_='pkmn-name')
                            if not name_div:
                                continue
                            boss_name = name_div.get_text(" ", strip=True)
                            key = (boss_name.lower(), tier, start_date, end_date)
                            if boss_name and key not in seen_scheduled:
                                seen_scheduled.add(key)
                                final_data["scheduled_bosses"].append({
                                    "name": boss_name,
                                    "tier": tier,
                                    "start": start_date,
                                    "end": end_date,
                                })
                except Exception as ex:
                    print(f"Skipping event detail {link}: {ex}")

        print(f"Successfully loaded {len(final_data['events'])} events and {len(final_data['scheduled_bosses'])} scheduled bosses.")
    except Exception as e:
        print(f"Error scraping events: {e}")
    
    # --- SAVE ---
    os.makedirs('api', exist_ok=True)
    with open('api/raidboss.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)
    print("Successfully updated api/raidboss.json.")

if __name__ == "__main__":
    scrape_data()
