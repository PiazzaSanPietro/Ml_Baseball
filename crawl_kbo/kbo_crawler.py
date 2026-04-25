import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os

BASE_URL = "https://www.koreabaseball.com"
OUTPUT_DIR = "data"
YEARS = list(range(2022, 2027))

TARGETS = {
    # 선수 기록
    "타자_기본기록": "/Record/Player/HitterBasic/Basic1.aspx",
    "타자_세부기록": "/Record/Player/HitterBasic/Detail1.aspx",
    "투수_기본기록": "/Record/Player/PitcherBasic/Basic1.aspx",
    "투수_세부기록": "/Record/Player/PitcherBasic/Detail1.aspx",
    "수비_기본기록": "/Record/Player/Defense/Basic.aspx",
    "주루_기본기록": "/Record/Player/Runner/Basic.aspx",
    # 팀 기록
    "팀_타자_기본기록": "/Record/Team/Hitter/Basic1.aspx",
    "팀_타자_세부기록": "/Record/Team/Hitter/Detail1.aspx",
    "팀_투수_기본기록": "/Record/Team/Pitcher/Basic1.aspx",
    "팀_투수_세부기록": "/Record/Team/Pitcher/Detail1.aspx",
    "팀_수비_기본기록": "/Record/Team/Defense/Basic.aspx",
    "팀_수비_세부기록": "/Record/Team/Defense/Detail.aspx",
    "팀_주루_기본기록": "/Record/Team/Runner/Basic.aspx",
    "팀_주루_세부기록": "/Record/Team/Runner/Detail.aspx",
    # 팀 순위
    "팀_순위": "/Record/TeamRank/TeamRank.aspx",
}

SEASON_FIELD = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeason$ddlSeason"

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


def extract_form_fields(soup):
    """form 내 모든 input + select 필드 추출"""
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
    """javascript:__doPostBack('target','arg') 에서 target 추출"""
    inner = href[href.find("(") + 1 : href.rfind(")")]
    parts = [p.strip().strip("'\"") for p in inner.split(",")]
    return parts[0] if parts else None


def get_pager_info(soup):
    """페이지네이션 버튼 정보 반환: {page_num(int): target, "다음": target}"""
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


def parse_table(soup):
    """메인 데이터 테이블 파싱. (headers, rows) 반환"""
    table = (
        soup.find("table", class_="tData")
        or soup.select_one("div.record_wrap table")
        or soup.select_one("div#cphContents_cphContents_cphContents_udpContent table")
        or soup.find("table")
    )
    if not table:
        return [], []

    thead = table.find("thead")
    if thead:
        headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
    else:
        first_tr = table.find("tr")
        headers = (
            [cell.get_text(strip=True) for cell in first_tr.find_all(["th", "td"])]
            if first_tr
            else []
        )

    tbody = table.find("tbody") or table
    rows = []
    for tr in tbody.find_all("tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cols:
            rows.append(cols)

    return headers, rows


def switch_year(session, url, soup, year):
    """연도 드롭다운 변경 POST → 해당 연도 첫 페이지 soup 반환"""
    fields = extract_form_fields(soup)
    fields[SEASON_FIELD] = str(year)
    fields["__EVENTTARGET"] = SEASON_FIELD
    fields["__EVENTARGUMENT"] = ""
    resp = session.post(url, data=fields, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def crawl_record(name, path, year):
    url = BASE_URL + path
    session = requests.Session()
    all_rows = []
    headers = []
    current_page = 1

    # 1. GET (기본 연도 페이지)
    resp = session.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 2. 원하는 연도로 전환
    soup = switch_year(session, url, soup, year)
    time.sleep(0.5)

    # 3. 전 페이지 수집
    while True:
        h, rows = parse_table(soup)
        if not rows:
            break

        if not headers and h:
            headers = h
        all_rows.extend(rows)
        current_page_label = f"{year}년 {current_page}페이지"
        print(f"    {current_page_label}: {len(rows)}행 (누계 {len(all_rows)}행)")

        pager = get_pager_info(soup)
        next_target = pager.get(current_page + 1)

        # 다음 버튼으로 페이지 그룹 이동
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

    return headers, all_rows


def save_csv(name, year, headers, rows):
    year_dir = os.path.join(OUTPUT_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)
    df = pd.DataFrame(rows, columns=headers if len(headers) == len(rows[0]) else None)
    filepath = os.path.join(year_dir, f"{name}.csv")
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    return filepath, len(df)


def main():
    total_files = 0
    errors = []

    for year in YEARS:
        print(f"\n{'='*40}")
        print(f"  {year}년 크롤링 시작")
        print(f"{'='*40}")

        for name, path in TARGETS.items():
            filepath = os.path.join(OUTPUT_DIR, str(year), f"{name}.csv")
            if os.path.exists(filepath):
                print(f"\n  [{name}] → 이미 존재, 건너뜀 ({filepath})")
                continue

            print(f"\n  [{name}]")
            try:
                headers, rows = crawl_record(name, path, year)
                if rows:
                    filepath, count = save_csv(name, year, headers, rows)
                    print(f"    → 저장: {filepath} (총 {count}행)")
                    total_files += 1
                else:
                    print(f"    → 데이터 없음 (건너뜀)")
            except Exception as e:
                msg = f"{year}년 {name}: {e}"
                print(f"    → 오류: {e}")
                errors.append(msg)
            time.sleep(1)

    print(f"\n{'='*40}")
    print(f"전체 완료: {total_files}개 파일 저장")
    if errors:
        print(f"오류 {len(errors)}건:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()
