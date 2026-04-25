"""일자별 팀 순위 크롤러 (2022~2026)

TeamRankDaily 페이지는 날짜 텍스트 입력 방식으로 날짜를 이동합니다.
hfNextDate hidden 필드를 따라가며 경기가 있는 날만 순회합니다.
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
from kbo_crawler import extract_form_fields, BASE_URL, REQUEST_HEADERS, YEARS

TARGET_PATH = "/Record/TeamRank/TeamRankDaily.aspx"
TARGET_NAME = "팀_일자별순위"
URL = BASE_URL + TARGET_PATH

PREFIX = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$"
F_DATE_INPUT = PREFIX + "txtCanlendar"
F_HF_DATE = PREFIX + "hfSearchDate"
F_HF_NEXT = PREFIX + "hfNextDate"
F_HF_PREV = PREFIX + "hfPrevDate"
F_BTN = PREFIX + "btnCalendarSelect"
F_SERIES = PREFIX + "ddlSeries"


def _extract_fields(soup):
    """image 타입 버튼을 제외한 form 필드 추출"""
    fields = {}
    form = soup.find("form", id="mainForm") or soup.find("form")
    if not form:
        return fields
    for inp in form.find_all("input"):
        name = inp.get("name", "")
        if name and inp.get("type", "").lower() != "image":
            fields[name] = inp.get("value", "")
    for sel in form.find_all("select"):
        name = sel.get("name", "")
        if name:
            selected = sel.find("option", selected=True)
            fields[name] = selected.get("value", "") if selected else ""
    return fields


def _post_date(session, fields, date_str):
    """특정 날짜로 이동하는 POST 요청"""
    fields = dict(fields)
    fields["__EVENTTARGET"] = ""
    fields["__EVENTARGUMENT"] = ""
    fields[F_DATE_INPUT] = date_str
    fields[F_HF_DATE] = date_str
    fields[F_SERIES] = "0"  # 정규시즌
    resp = session.post(URL, data=fields, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _parse_table(soup):
    """순위 테이블 파싱 → rows 반환 (headers 포함)"""
    table = soup.find("table", class_="tData") or soup.find("table")
    if not table:
        return [], []
    thead = table.find("thead")
    if thead:
        headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
    else:
        first_tr = table.find("tr")
        headers = [c.get_text(strip=True) for c in first_tr.find_all(["th", "td"])] if first_tr else []
    tbody = table.find("tbody") or table
    rows = []
    for tr in tbody.find_all("tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cols:
            rows.append(cols)
    return headers, rows


def crawl_daily_rank_year(year):
    """한 시즌의 일자별 팀 순위 전체 수집 → (headers, all_rows) 반환"""
    session = requests.Session()

    # 초기 GET으로 VIEWSTATE 등 획득
    resp = session.get(URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    fields = _extract_fields(soup)

    # 연도 초(1월 1일)로 이동 → hfNextDate가 해당 연도 첫 경기일을 가리킴
    soup = _post_date(session, fields, f"{year}0101")
    time.sleep(0.5)

    fields = _extract_fields(soup)
    current_date = fields.get(F_HF_NEXT, "").strip()

    # 첫 경기일이 대상 연도가 아니면 데이터 없음
    if not current_date or not current_date.startswith(str(year)):
        print(f"  {year}년 경기 데이터 없음 (hfNextDate={current_date!r})")
        return [], []

    all_rows = []
    table_headers = []
    date_count = 0

    while current_date and current_date.startswith(str(year)):
        soup = _post_date(session, fields, current_date)
        time.sleep(0.3)

        t_headers, rows = _parse_table(soup)
        if rows:
            if not table_headers and t_headers:
                table_headers = ["날짜"] + t_headers
            for row in rows:
                all_rows.append([current_date] + row)
            date_count += 1
            if date_count % 20 == 0:
                print(f"    {current_date}: 누계 {len(all_rows)}행")

        fields = _extract_fields(soup)
        current_date = fields.get(F_HF_NEXT, "").strip()

    print(f"    완료: {date_count}일치, {len(all_rows)}행")
    return table_headers, all_rows


def main():
    os.makedirs("data", exist_ok=True)
    errors = []
    saved = 0

    for year in YEARS:
        filepath = os.path.join("data", str(year), f"{TARGET_NAME}.csv")
        if os.path.exists(filepath):
            print(f"\n[{year}년 {TARGET_NAME}] → 이미 존재, 건너뜀")
            continue

        print(f"\n[{year}년 {TARGET_NAME}] 크롤링 중...")
        try:
            headers, rows = crawl_daily_rank_year(year)
            if rows:
                year_dir = os.path.join("data", str(year))
                os.makedirs(year_dir, exist_ok=True)
                df = pd.DataFrame(rows, columns=headers if headers and len(headers) == len(rows[0]) else None)
                df.to_csv(filepath, index=False, encoding="utf-8-sig")
                print(f"  → 저장: {filepath} (총 {len(df)}행)")
                saved += 1
            else:
                print(f"  → 데이터 없음")
        except Exception as e:
            msg = f"{year}년 {TARGET_NAME}: {e}"
            print(f"  → 오류: {e}")
            errors.append(msg)
        time.sleep(1)

    print(f"\n완료: {saved}개 파일 저장")
    if errors:
        print(f"오류 {len(errors)}건:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
