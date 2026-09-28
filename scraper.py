import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone

def scrape_data():
    print("Starte den perfekten Scraper für Nikolaj-kun! 🌸")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    final_data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "raids": [],
        "max_battles": []
    }

    # --- 1. LEEKDUCK RAIDS SCRAPEN ---
    try:
        ld_response = requests.get("https://leekduck.com/raid-bosses/", headers=headers)
        ld_soup = BeautifulSoup(ld_response.text, 'html.parser')
        
        # Normale Raids und Shadow Raids finden
        for raid_container in ld_soup.find_all('div', class_=['raid-bosses', 'shadow-raid-bosses']):
            for tier_group in raid_container.find_all('div', class_='tier'):
                tier_name = tier_group.find('h2').get('data-tier', 'Unknown')
                
                for card in tier_group.find_all('div', class_='card'):
                    name = card.find('p', class_='name').text.strip()
                    img_tag = card.find('div', class_='boss-img').find('img')
                    img_url = img_tag['src'] if img_tag else ""
                    if not img_url.startswith('http'):
                        img_url = f"https://leekduck.com{img_url}"
                        
                    final_data["raids"].append({
                        "name": name,
                        "tier": tier_name,
                        "image": img_url,
                        "is_shadow": 'shadow-raid-bosses' in raid_container.get('class', [])
                    })
        print(f"✅ {len(final_data['raids'])} Raids von LeekDuck geladen!")
    except Exception as e:
        print(f"❌ Fehler bei LeekDuck: {e}")

    # --- 2. MINPOKE MAX BATTLES SCRAPEN ---
    try:
        mp_response = requests.get("https://9db.jp/pokemongo/data/20859", headers=headers)
        mp_soup = BeautifulSoup(mp_response.text, 'html.parser')
        
        # Der erste Tab beinhaltet die aktuell laufenden Max Battles
        current_tab = mp_soup.find('div', id='wiki_tab0')
        if current_tab:
            for boss_span in current_tab.find_all('span', class_='wiki_tier_boss'):
                # Der Name steht im zweiten inneren Span mit grauem Hintergrund
                name_span = boss_span.find_all('span', recursive=False)[-1]
                # Den Text extrahieren (ohne die HTML-Tags)
                name = name_span.text.strip()
                
                # Bild extrahieren
                img_tag = boss_span.find('img', class_='wiki_dmax')
                img_url = img_tag['src'] if img_tag else ""
                
                final_data["max_battles"].append({
                    "name_jp": name,
                    "image": img_url
                })
        print(f"✅ {len(final_data['max_battles'])} Max Battles von Minpoke geladen!")
    except Exception as e:
        print(f"❌ Fehler bei Minpoke: {e}")

    # --- JSON SPEICHERN ---
    os.makedirs('api', exist_ok=True)
    with open('api/raidboss.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)
    print("🎉 Alles erfolgreich als api/raidboss.json gespeichert!")

if __name__ == "__main__":
    scrape_data()
