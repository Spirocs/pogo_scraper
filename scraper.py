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
                        "image": img_url,
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
            for boss_span in current_tab.find_all('span', class_='wiki_tier_boss'):
                name_span = boss_span.find_all('span', recursive=False)[-1]
                name = name_span.text.strip()
                
                img_tag = boss_span.find('img', class_='wiki_dmax')
                img_url = img_tag['src'] if img_tag else ""
                
                final_data["max_battles"].append({
                    "name_jp": name,
                    "image": img_url
                })
        print(f"Successfully loaded {len(final_data['max_battles'])} max battles.")
    except Exception as e:
        print(f"Error scraping max battles: {e}")

    # --- 3. LEEKDUCK EVENTS ---
    try:
        ev_response = requests.get("https://leekduck.com/events/", headers=headers)
        ev_soup = BeautifulSoup(ev_response.text, 'html.parser')
        
        for item in ev_soup.find_all('span', class_='event-header-item-wrapper'):
            title_tag = item.find('h2')
            if not title_tag:
                continue
                
            title = title_tag.text.strip()
            event_type = item.get('data-event-type', 'event')
            start_date = item.get('data-event-start-date') or item.get('data-event-start-date-check')
            end_date = item.get('data-event-end-date') or item.get('data-event-date-sort')
            is_local = item.get('data-event-local-time') == 'true'
            
            img_tag = item.find('span', class_='event-img-wrapper')
            img_url = ""
            if img_tag and img_tag.find('img'):
                img_url = img_tag.find('img').get('src', '')

            link_tag = item.find('a', class_='event-item-link')
            link = f"https://leekduck.com{link_tag['href']}" if link_tag and 'href' in link_tag.attrs else ""

            final_data["events"].append({
                "title": title,
                "type": event_type,
                "start": start_date,
                "end": end_date,
                "is_local_time": is_local,
                "image": img_url,
                "link": link
            })
        print(f"Successfully loaded {len(final_data['events'])} events.")
    except Exception as e:
        print(f"Error scraping events: {e}")

    # --- SAVE ---
    os.makedirs('api', exist_ok=True)
    with open('api/raidboss.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)
    print("Successfully updated api/raidboss.json.")

if __name__ == "__main__":
    scrape_data()
