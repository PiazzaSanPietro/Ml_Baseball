import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import re

BASE_URL = "https://www.koreabaseball.com"
OUTPUT_DIR = "data"
YEAR = 2026
GAME_TYPE_CODE = 1  # KBO 정규시즌

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

SEASON_FIELD = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeason$ddlSeason"

PLAYER_LIST_PATHS = {
    "타자": "/Record/Player/HitterBasic/Basic1.aspx",
    "투수": "/Record/Player/PitcherBasic/Basic1.aspx",
}

DETAIL_DIRS = {
    "타자": "HitterDetail",
    "투수": "PitcherDetail",
}

# (탭 이름, 파일명, 연도/게임타입 파라미터 사용 여부)
PROFILE_TABS = [
    ("통산기록",   "Total.aspx",     False),
    ("일자별기록", "Daily.aspx",     True),
    ("경기별기록", "Game.aspx",      True),
    ("상황별기록", "Situation.aspx", True),
]


# ──────────────────────────────────────────
#  PostBack 공용 헬퍼 (선수 목록 페이지 페이지네이션용)
# ──────────────────────────────────────────

def extract_form_fields(soup):
    fields = {}
    form = soup.find("form", id="mainForm") or soup.find("form")
    if not form:
        return fields
    for inp in form.find_all("input"):
        name = inp.get("name", "")
        if name:
            fields[name] = inp.get("value", "")
    for sel in form.find_all("select"):
        name = sel.get("name", "")
        if name:
            selected = sel.find("option", selected=True)
            fields[name] = selected.get("value", "") if selected else ""
    return fields


def parse_postback_target(href):
    inner = href[href.find("(") + 1: href.rfind(")")]
    parts = [p.strip().strip("'\"") for p in inner.split(",")]
    return parts[0] if parts else None


def get_pager_info(soup):
    info = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "__doPostBack" not in href or "ucPager" not in href:
            continue
        target = parse_postback_target(href)
        if not target:
            continue
        text = a.get_text(strip=True)
        if text.isdigit():
            info[int(text)] = target
        elif text in ("다음", ">", "▶"):
            info["다음"] = target
    return info


def switch_year(session, url, soup, year):
    fields = extract_form_fields(soup)
    fields[SEASON_FIELD] = str(year)
    fields["__EVENTTARGET"] = SEASON_FIELD
    fields["__EVENTARGUMENT"] = ""
    resp = session.post(url, data=fields, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ──────────────────────────────────────────
#  선수 ID 수집
# ──────────────────────────────────────────

def extract_player_ids_from_soup(soup, position):
    """현재 페이지 테이블의 링크에서 선수 ID·이름 추출"""
    players = {}
    detail_dir = DETAIL_DIRS[position]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if detail_dir in href and "playerId=" in href:
            m = re.search(r"playerId=(\d+)", href)
            if m:
                pid = m.group(1)
                name = a.get_text(strip=True)
                if name:
                    players[pid] = name
    return players


def crawl_all_player_ids(position, year):
    """선수 목록 페이지를 전체 페이지네이션하며 선수 ID 수집"""
    path = PLAYER_LIST_PATHS[position]
    url = BASE_URL + path
    session = requests.Session()
    all_players = {}
    current_page = 1

    print(f"  [{position}] 선수 목록 수집 중...")
    resp = session.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    soup = switch_year(session, url, soup, year)
    time.sleep(0.5)

    while True:
        players = extract_player_ids_from_soup(soup, position)
        if not players:
            break
        new_cnt = sum(1 for pid in players if pid not in all_players)
        all_players.update(players)
        print(f"    페이지 {current_page}: {len(players)}명 (신규 {new_cnt}명, 누계 {len(all_players)}명)")

        pager = get_pager_info(soup)
        next_target = pager.get(current_page + 1)

        if not next_target and "다음" in pager:
            fields = extract_form_fields(soup)
            fields["__EVENTTARGET"] = pager["다음"]
            fields["__EVENTARGUMENT"] = ""
            time.sleep(0.5)
            resp = session.post(url, data=fields, headers=REQUEST_HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            pager = get_pager_info(soup)
            next_target = pager.get(current_page + 1)

        if not next_target:
            break

        fields = extract_form_fields(soup)
        fields["__EVENTTARGET"] = next_target
        fields["__EVENTARGUMENT"] = ""
        time.sleep(0.5)
        resp = session.post(url, data=fields, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        current_page += 1

    return all_players


# ──────────────────────────────────────────
#  테이블 파싱
# ──────────────────────────────────────────

def parse_table_element(table):
    """단일 <table> 요소에서 (headers, rows) 반환"""
    thead = table.find("thead")
    if thead:
        headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
    else:
        first_tr = table.find("tr")
        headers = (
            [c.get_text(strip=True) for c in first_tr.find_all(["th", "td"])]
            if first_tr else []
        )

    tbody = table.find("tbody") or table
    rows = []
    for tr in tbody.find_all("tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cols:
            rows.append(cols)

    return headers, rows


def parse_page_tables(soup):
    """
    div.player_records 하위의 데이터 테이블을 섹션 제목과 함께 파싱.
    반환: [(section_name_or_None, headers, rows), ...]

    구조:
      - Game/Situation: h5.bul_sub → div.tbl-type02 → table  (섹션명 존재)
      - Daily: div.tbl-type02 → table  (헤더 첫 셀에 월 이름 포함)
      - Total: div.tbl-type02 → table  (단일 테이블, 섹션 없음)
    """
    pr = soup.find("div", class_="player_records") or soup.body or soup

    current_section = None
    results = []

    for child in pr.children:
        if not hasattr(child, "name") or not child.name:
            continue
        if child.name == "h5" and "bul_sub" in child.get("class", []):
            current_section = child.get_text(strip=True)
        elif "tbl-type02" in child.get("class", []):
            table = child.find("table")
            if not table:
                continue
            headers, rows = parse_table_element(table)
            if not rows:
                continue
            section = current_section
            # Daily.aspx: 헤더 첫 셀이 'N월' 형태인 경우 월 이름을 섹션으로 사용
            if section is None and headers and re.match(r"^\d+월$", headers[0]):
                section = headers[0]
                headers = ["날짜"] + headers[1:]
            results.append((section, headers, rows))

    return results


# ──────────────────────────────────────────
#  저장
# ──────────────────────────────────────────

def get_output_path(player_name, player_id, position, tab_name):
    safe = re.sub(r'[\\/:*?"<>|]', "_", player_name)
    pos_dir = os.path.join(OUTPUT_DIR, str(YEAR), "프로필", position)
    return os.path.join(pos_dir, f"{safe}_{player_id}_{tab_name}.csv")


def save_sections_csv(player_name, player_id, position, tab_name, sections):
    """
    sections 리스트를 단일 CSV로 저장.
    섹션이 여러 개이거나 섹션 이름이 있으면 '분류' 컬럼을 앞에 추가.
    """
    filepath = get_output_path(player_name, player_id, position, tab_name)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    if not sections:
        return None, 0

    has_label = len(sections) > 1 or sections[0][0] is not None
    frames = []

    for section_name, headers, rows in sections:
        if not rows:
            continue
        try:
            if headers and len(headers) == len(rows[0]):
                df_part = pd.DataFrame(rows, columns=headers)
            else:
                df_part = pd.DataFrame(rows)
        except Exception:
            df_part = pd.DataFrame(rows)

        if has_label and section_name:
            df_part.insert(0, "분류", section_name)

        frames.append(df_part)

    if not frames:
        return None, 0

    df = pd.concat(frames, ignore_index=True)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    return filepath, len(df)


# ──────────────────────────────────────────
#  선수 기본 프로필 파싱
# ──────────────────────────────────────────

def extract_player_info(soup, player_id, position):
    """
    div.player_info에서 선수 기본 정보를 딕셔너리로 반환.
    필드: 선수ID, 포지션구분, 팀명, 선수명, 등번호, 생년월일,
          포지션, 신장/체중, 경력, 계약보너스, 연봉, 드래프트, 입단년도
    """
    info = {"선수ID": player_id, "포지션구분": position}

    pi = soup.find("div", class_="player_info")
    if not pi:
        return info

    # 팀명 — h4.team
    h4 = pi.find("h4", class_="team")
    if h4:
        info["팀명"] = h4.get_text(strip=True)

    # 세부 필드 — div.player_basic > ul > li
    pb = pi.find("div", class_="player_basic")
    if not pb:
        return info

    for li in pb.find_all("li"):
        # <li><strong>레이블:</strong><span>값</span></li> 구조
        strong = li.find("strong")
        span = li.find("span")
        if strong and span:
            label = strong.get_text(strip=True).rstrip(":")
            value = span.get_text(strip=True)
            info[label] = value
        else:
            # 대체: li 전체 텍스트를 ':' 기준으로 분리
            text = li.get_text(strip=True)
            if ":" in text:
                label, _, value = text.partition(":")
                info[label.strip()] = value.strip()

    return info


def save_player_info_csv(player_name, player_id, position, info):
    filepath = get_output_path(player_name, player_id, position, "프로필")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df = pd.DataFrame([info])
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    return filepath


# ──────────────────────────────────────────
#  선수 프로필 크롤링
# ──────────────────────────────────────────

def crawl_player_profile(session, player_id, player_name, position):
    """프로필 정보 + 4개 탭(통산/일자별/경기별/상황별) 크롤링 → CSV 저장"""
    detail_dir = DETAIL_DIRS[position]
    saved = 0

    # ── 기본 프로필 (Basic.aspx) ──────────────
    info_path = get_output_path(player_name, player_id, position, "프로필")
    if os.path.exists(info_path):
        print(f"      [프로필] 건너뜀 (기존 파일)")
    else:
        try:
            url = f"{BASE_URL}/Record/Player/{detail_dir}/Basic.aspx?playerId={player_id}"
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            info = extract_player_info(soup, player_id, position)
            save_player_info_csv(player_name, player_id, position, info)
            fields = len(info) - 2  # 선수ID, 포지션구분 제외
            print(f"      [프로필] {fields}개 항목 저장")
            saved += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"      [프로필] 오류: {e}")
            time.sleep(1)

    # ── 기록 탭 4개 ───────────────────────────
    for tab_name, tab_file, use_year in PROFILE_TABS:
        filepath = get_output_path(player_name, player_id, position, tab_name)
        if os.path.exists(filepath):
            print(f"      [{tab_name}] 건너뜀 (기존 파일)")
            continue

        try:
            if use_year:
                url = (
                    f"{BASE_URL}/Record/Player/{detail_dir}/{tab_file}"
                    f"?playerId={player_id}&seasonCode={YEAR}&gameTypeCode={GAME_TYPE_CODE}"
                )
            else:
                url = f"{BASE_URL}/Record/Player/{detail_dir}/{tab_file}?playerId={player_id}"

            resp = session.get(url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            sections = parse_page_tables(soup)
            if sections:
                fp, count = save_sections_csv(player_name, player_id, position, tab_name, sections)
                if fp:
                    print(f"      [{tab_name}] {count}행 저장")
                    saved += 1
                else:
                    print(f"      [{tab_name}] 저장 실패")
            else:
                print(f"      [{tab_name}] 데이터 없음")

            time.sleep(0.3)

        except Exception as e:
            print(f"      [{tab_name}] 오류: {e}")
            time.sleep(1)

    return saved


# ──────────────────────────────────────────
#  메인
# ──────────────────────────────────────────

def main():
    session = requests.Session()
    total_files = 0
    errors = []

    for position in ["타자", "투수"]:
        print(f"\n{'='*55}")
        print(f"  {YEAR}년 KBO 정규시즌  {position} 프로필 크롤링")
        print(f"{'='*55}")

        players = crawl_all_player_ids(position, YEAR)
        print(f"  → 수집된 선수: 총 {len(players)}명\n")

        for i, (pid, name) in enumerate(players.items(), 1):
            print(f"  [{i:>3}/{len(players)}] {name} (ID: {pid})")
            try:
                saved = crawl_player_profile(session, pid, name, position)
                total_files += saved
            except Exception as e:
                msg = f"{position}/{name}({pid}): {e}"
                print(f"    오류: {e}")
                errors.append(msg)
            time.sleep(0.5)

    print(f"\n{'='*55}")
    print(f"완료: 총 {total_files}개 파일 저장")
    if errors:
        print(f"오류 {len(errors)}건:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
