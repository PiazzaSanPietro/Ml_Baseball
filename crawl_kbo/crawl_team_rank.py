"""팀 순위 전용 크롤러 (2022~2026)
TeamRank 페이지는 ddlYear 필드를 사용 (다른 페이지의 ddlSeason과 다름)
"""
import requests
from bs4 import BeautifulSoup
import time
import os
from kbo_crawler import (
    extract_form_fields, parse_table, save_csv,
    BASE_URL, REQUEST_HEADERS, YEARS,
)

TARGET_NAME = "팀_순위"
TARGET_PATH = "/Record/TeamRank/TeamRank.aspx"
YEAR_FIELD = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlYear"


def crawl_team_rank(year):
    url = BASE_URL + TARGET_PATH
    session = requests.Session()

    resp = session.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 연도 전환
    fields = extract_form_fields(soup)
    fields[YEAR_FIELD] = str(year)
    fields["__EVENTTARGET"] = YEAR_FIELD
    fields["__EVENTARGUMENT"] = ""
    resp = session.post(url, data=fields, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    time.sleep(0.5)

    return parse_table(soup)


errors = []
saved = 0

for year in YEARS:
    filepath = os.path.join("data", str(year), f"{TARGET_NAME}.csv")
    if os.path.exists(filepath):
        os.remove(filepath)  # 기존 잘못된 파일 제거 후 재크롤링

    print(f"\n[{year}년 팀 순위] 크롤링 중...")
    try:
        headers, rows = crawl_team_rank(year)
        if rows:
            fp, count = save_csv(TARGET_NAME, year, headers, rows)
            print(f"  → 저장: {fp} (총 {count}행)")
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
