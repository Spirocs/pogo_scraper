import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, timezone

def parse_minpoke_period(period_text, current_year):
    """
    Parses Minpoke local date ranges like '11/13(金)6:00～11/13(金)21:00'
    or '11/9(月)5:00～11/13(金)21:00' into ISO local strings ('YYYY-MM-DDTHH:MM:00').
    """
    pattern = r'(\d{1,2})/(\d{1,2})\([^)]+\)\s*(\d{1,2}):(\d{2})\s*[～〜~-]\s*(?:(\d{1,2})/(\d{1,2})\([^)]+\)\s*)?(\d{1,2}):(\d{2})'
    match = re.search(pattern, period_text)
    if not match:
        return None, None

    s_month, s_day, s_hour, s_min, e_month, e_day, e_hour, e_min = match.groups()
    s_m, s_d, s_h, s_mn = int(s_month), int(s_day), int(s_hour), int(s_min)
    e_m = int(e_month) if e_month else s_m
    e_d = int(e_day) if e_day else s_d
    e_h, e_mn = int(e_hour), int(e_min)

    start_year = current_year
    end_year = current_year + 1 if (e_m < s_m) else current_year

    start_iso = f"{start_year:04d}-{s_m:02d}-{s_d:02d}T{s_h:02d}:{s_mn:02d}:00"
    end_iso = f"{end_year:04d}-{e_m:02d}-{e_d:02d}T{e_h:02d}:{e_mn:02d}:00"
    return start_iso, end_iso

def parse_leekduck_selector_dates(selector_div):
    """
    Extracts Starts/Ends local time strings from LeekDuck's .raid-time-labels
    e.g. 'Nov 9, 2026, 10:00 AM' -> '2026-11-09T10:00:00'
    """
    if not selector_div:
        return None, None
    start_iso, end_iso = None, None
    for row in selector_div.find_all('div', class_='time-row'):
        label = row.find('span', class_='time-label')
        val = row.find('span', class_='time-value')
        if not label or not val:
            continue
        text_val = val.text.strip()
        try:
            dt = datetime.strptime(text_val, "%b %d, %Y, %I:%M %p")
            iso_str = dt.strftime("%Y-%m-%dT%H:%M:00")
            if 'Start' in label.text:
                start_iso = iso_str
            elif 'End' in label.text:
                end_iso = iso_str
        except ValueError:
            pass
    return start_iso, end_iso

def scrape_data():
    print("Starting hybrid scraper (LeekDuck + Minpoke Raids & Max Battles)...")
    now_utc = datetime.now(timezone.utc)
    cache_buster = int(now_utc.timestamp())
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

    final_data = {
        "last_updated": now_utc.isoformat(),
        "raids": [],
        "max_battles": [],
        "events": [],
        "scheduled_bosses": []
    }

    seen_scheduled = set()

    # --- 1. LEEKDUCK RAIDS ---
    try:
        ld_response = requests.get(f"https://leekduck.com/raid-bosses/?t={cache_buster}", headers=headers, timeout=15)
        ld_soup = BeautifulSoup(ld_response.text, 'html.parser')

        reg_start, reg_end = parse_leekduck_selector_dates(ld_soup.find('div', id='regular-raid-selector'))
        shd_start, shd_end = parse_leekduck_selector_dates(ld_soup.find('div', id='shadow-raid-selector'))

        for raid_container in ld_soup.find_all('div', class_=['raid-bosses', 'shadow-raid-bosses']):
            is_shadow_container = 'shadow-raid-bosses' in raid_container.get('class', [])
            c_start = shd_start if is_shadow_container else reg_start
            c_end = shd_end if is_shadow_container else reg_end

            for tier_group in raid_container.find_all('div', class_='tier'):
                h2_tag = tier_group.find('h2')
                tier_name = h2_tag.get('data-tier', 'Unknown') if h2_tag else 'Unknown'

                for card in tier_group.find_all('div', class_='card'):
                    name_tag = card.find('p', class_='name')
                    if not name_tag:
                        continue
                    name = name_tag.text.strip()

                    final_data["raids"].append({
                        "name": name,
                        "tier": tier_name,
                        "is_shadow": is_shadow_container,
                        "start": c_start,
                        "end": c_end,
                        "source": "leekduck"
                    })
        print(f"Successfully loaded {len(final_data['raids'])} raids from LeekDuck.")
    except Exception as e:
        print(f"Error scraping LeekDuck raids: {e}")

    # --- 2. MINPOKE RAIDS (data/2308: ALL TABS + MONTHLY SCHEDULE) ---
    try:
        mp_raid_url = f"https://9db.jp/pokemongo/data/2308?t={cache_buster}"
        mp_raid_resp = requests.get(mp_raid_url, headers=headers, timeout=15)
        mp_raid_soup = BeautifulSoup(mp_raid_resp.text, 'html.parser')

        for tab_div in mp_raid_soup.find_all('div', id=re.compile(r'^wiki_tab\d+$')):
            start_iso, end_iso = None, None
            period_table = tab_div.find('table', class_='wiki_t_gray')
            if period_table:
                period_text = period_table.get_text(" ", strip=True)
                start_iso, end_iso = parse_minpoke_period(period_text, now_utc.year)

            current_tier = "5"
            for element in tab_div.find_all(['table', 'p']):
                if element.name == 'table' and 'wiki_noborder' in element.get('class', []):
                    img_tag = element.find('img', src=lambda s: s and 'raid' in s)
                    if img_tag and 'src' in img_tag.attrs:
                        src = img_tag['src']
                        if 'raid5' in src:
                            current_tier = "5"
                        elif 'raid3' in src:
                            current_tier = "3"
                        elif 'raid1' in src:
                            current_tier = "1"
                        elif 'mega' in src or 'raid4' in src:
                            current_tier = "Mega"
                elif element.name == 'p':
                    for boss_span in element.find_all('span', class_='wiki_tier_boss'):
                        bold_spans = boss_span.find_all('span', class_='wiki_disp_b')
                        if not bold_spans:
                            continue
                        jp_name = bold_spans[-1].get_text(strip=True)
                        is_shadow = boss_span.find('img', src=lambda s: s and 'shadow.png' in s) is not None

                        final_data["raids"].append({
                            "name_jp": jp_name,
                            "tier": current_tier,
                            "is_shadow": is_shadow,
                            "start": start_iso,
                            "end": end_iso,
                            "source": "minpoke"
                        })

        # Also scrape Minpoke's monthly forecast table (伝説・メガレイドの出現予定) with Event Override detection
        infograph = mp_raid_soup.find('div', class_='wiki_infograph')
        if infograph:
            override_start_iso = None
            override_end_iso = None
            override_note = infograph.find('table', class_='wiki_modew')
            if override_note:
                note_text = override_note.get_text(" ", strip=True)
                ov_match = re.search(
                    r'(\d{1,2})月(\d{1,2})日\([^)]+\)\s*(\d{1,2}):(\d{2})から\s*(\d{1,2})月(\d{1,2})日',
                    note_text
                )
                if ov_match:
                    om1, od1, oh1, omn1, om2, od2 = [int(x) for x in ov_match.groups()]
                    override_start_iso = f"{now_utc.year:04d}-{om1:02d}-{od1:02d}T{oh1:02d}:{omn1:02d}:00"
                    override_end_iso = f"{now_utc.year:04d}-{om2:02d}-{od2:02d}T21:00:00"

            for h3 in infograph.find_all('h3'):
                h3_text = h3.get_text(strip=True)
                sched_tier = "5-star"
                is_shadow_sched = False
                if "メガ" in h3_text:
                    sched_tier = "Mega"
                elif "シャドウ" in h3_text:
                    sched_tier = "Shadow"
                    is_shadow_sched = True

                table = h3.find_next_sibling('table')
                if not table:
                    continue

                cells = table.find_all('td')
                parsed_cells = []
                for td in cells:
                    start_span = td.find('span', class_='wiki_pgodatetl')
                    end_span = td.find('span', class_='wiki_pgodatebr')
                    if not start_span:
                        continue

                    m_match = re.search(r'(\d{1,2})/(\d{1,2})', start_span.get_text(strip=True))
                    if not m_match:
                        continue
                    s_m, s_d = int(m_match.group(1)), int(m_match.group(2))
                    s_iso = f"{now_utc.year:04d}-{s_m:02d}-{s_d:02d}T05:00:00"

                    e_iso = None
                    if end_span:
                        e_match = re.search(r'(\d{1,2})/(\d{1,2})', end_span.get_text(strip=True))
                        if e_match:
                            e_m, e_d = int(e_match.group(1)), int(e_match.group(2))
                            e_year = now_utc.year + 1 if e_m < s_m else now_utc.year
                            e_iso = f"{e_year:04d}-{e_m:02d}-{e_d:02d}T21:00:00"

                    boss_links = [a.get_text(strip=True) for a in td.find_all('a') if a.get_text(strip=True)]
                    parsed_cells.append({
                        "start": s_iso,
                        "end": e_iso,
                        "bosses_jp": boss_links
                    })

                for i, cell in enumerate(parsed_cells):
                    end_val = cell["end"]
                    if not end_val and i + 1 < len(parsed_cells):
                        next_start = parsed_cells[i + 1]["start"]
                        # If an event override (like Wild Week 11/9-11/15) starts between this cell and the next cell,
                        # cap this rotation's end date at the start of the override!
                        if override_start_iso and cell["start"] < override_start_iso < next_start:
                            end_val = override_start_iso
                        else:
                            end_val = next_start
                    if not end_val:
                        continue

                    for b_jp in cell["bosses_jp"]:
                        key = (b_jp, sched_tier, cell["start"], end_val)
                        if key not in seen_scheduled:
                            seen_scheduled.add(key)
                            final_data["scheduled_bosses"].append({
                                "name_jp": b_jp,
                                "tier": sched_tier,
                                "is_shadow": is_shadow_sched,
                                "start": cell["start"],
                                "end": end_val,
                                "source": "minpoke"
                            })
        print("Successfully loaded Minpoke raid tabs and monthly forecast.")
    except Exception as e:
        print(f"Error scraping Minpoke raids: {e}")

    # --- 3. MINPOKE MAX BATTLES (data/20859: ALL TABS + TIMESTAMPS) ---
    try:
        mp_url = f"https://9db.jp/pokemongo/data/20859?t={cache_buster}"
        mp_response = requests.get(mp_url, headers=headers, timeout=15)
        mp_soup = BeautifulSoup(mp_response.text, 'html.parser')

        active_tab_num = "0"
        date_tab_table = mp_soup.find('table', id='wiki_date_tab')
        if date_tab_table:
            selected_td = date_tab_table.find('td', class_='wiki_selected')
            if selected_td:
                tab_link = selected_td.find('a', class_='wiki_tab')
                if tab_link and tab_link.get('data-num'):
                    active_tab_num = tab_link.get('data-num')

        for tab_div in mp_soup.find_all('div', id=re.compile(r'^wiki_tab\d+$')):
            tab_id = tab_div.get('id', '')
            tab_num = tab_id.replace('wiki_tab', '')
            is_active_tab = (tab_num == active_tab_num)

            start_iso, end_iso = None, None
            period_table = tab_div.find('table', class_='wiki_t_gray')
            if period_table:
                period_text = period_table.get_text(" ", strip=True)
                start_iso, end_iso = parse_minpoke_period(period_text, now_utc.year)

            current_level = 1
            for element in tab_div.find_all(['table', 'p']):
                if element.name == 'table' and 'wiki_noborder' in element.get('class', []):
                    icons = element.find_all('img', src=lambda s: s and 'w_boss.png' in s)
                    if len(icons) > 0:
                        current_level = len(icons)
                elif element.name == 'p':
                    for boss_span in element.find_all('span', class_='wiki_tier_boss'):
                        name_span = boss_span.find_all('span', recursive=False)[-1]
                        raw_jp_name = name_span.text.strip()
                        is_gmax = raw_jp_name.startswith("キョダイマックス") or current_level >= 6
                        clean_jp_name = (
                            raw_jp_name
                            .replace("キョダイマックス", "")
                            .replace("ダイマックス", "")
                            .strip()
                        )

                        final_data["max_battles"].append({
                            "name_jp": clean_jp_name,
                            "raw_name_jp": raw_jp_name,
                            "level": "tier_6" if is_gmax else f"tier_{current_level}",
                            "is_gmax": is_gmax,
                            "start": start_iso,
                            "end": end_iso,
                            "is_active_tab": is_active_tab
                        })
        print(f"Successfully loaded {len(final_data['max_battles'])} max battle entries from Minpoke.")
    except Exception as e:
        print(f"Error scraping max battles: {e}")

    # --- 4. LEEKDUCK EVENTS & SCHEDULED BOSSES ---
    try:
        ev_response = requests.get(f"https://leekduck.com/events/?t={cache_buster}", headers=headers, timeout=15)
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

        for ev in final_data["events"]:
            title = ev["title"]
            event_type = ev["type"]
            start_date = ev["start"]
            end_date = ev["end"]
            link = ev.get("link", "")

            if not start_date or not end_date or start_date == end_date:
                continue

            if event_type == 'raid-battles' and " in " in title:
                boss_name_raw = title.split(" in ")[0].strip()
                tier = "5-star"
                if "Mega" in title:
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
                        "source": "leekduck"
                    })

            elif event_type in ('event', 'wild-area', 'raid-day', 'pokémon-go-tour', 'go-fest') and link:
                try:
                    detail_resp = requests.get(link, headers=headers, timeout=10)
                    detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                    for h3 in detail_soup.find_all(['h2', 'h3', 'h4']):
                        heading_text = h3.get_text(" ", strip=True).lower()
                        if 'raid hour' in heading_text:
                            continue

                        tier = None
                        if '5-star raid' in heading_text or 'five-star raid' in heading_text:
                            tier = '5-star'
                        elif 'mega raid' in heading_text:
                            tier = 'Mega'
                        elif 'primal raid' in heading_text:
                            tier = 'Primal'
                        elif 'shadow raid' in heading_text and ('5-star' in heading_text or 'five-star' in heading_text):
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
                                    "source": "leekduck"
                                })
                except Exception as ex:
                    print(f"Skipping event detail {link}: {ex}")

        print(f"Successfully loaded {len(final_data['events'])} events and {len(final_data['scheduled_bosses'])} scheduled bosses.")
    except Exception as e:
        print(f"Error scraping events: {e}")

    os.makedirs('api', exist_ok=True)
    with open('api/raidboss.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)
    print("Successfully updated api/raidboss.json.")

if __name__ == "__main__":
    scrape_data()
