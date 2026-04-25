# KBO 공식 사이트 크롤링 팁

## 사이트 기본 정보

- **URL**: https://www.koreabaseball.com
- **기술 스택**: ASP.NET WebForms (PostBack 방식)
- **인코딩**: UTF-8

---

## 페이지 URL 구조

| 카테고리 | 기본기록 | 세부기록 |
|---|---|---|
| 타자 | `/Record/Player/HitterBasic/Basic1.aspx` | `/Record/Player/HitterBasic/Detail1.aspx` |
| 투수 | `/Record/Player/PitcherBasic/Basic1.aspx` | `/Record/Player/PitcherBasic/Detail1.aspx` |
| 수비 | `/Record/Player/Defense/Basic.aspx` | 없음 |
| 주루 | `/Record/Player/Runner/Basic.aspx` | 없음 |

---

## ASP.NET PostBack 페이지네이션 처리

### 핵심 구조
- 페이지 이동이 `<a href="javascript:__doPostBack(...)">` 방식으로 동작
- `onclick` 이 아닌 **`href` 속성**에 postback 정보가 있음 (BeautifulSoup에서 `onclick=True`로 찾으면 못 찾음)
- 페이지네이션 버튼 ID 패턴:
  ```
  ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnNo1  (1페이지)
  ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnNo2  (2페이지)
  ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnLast (마지막)
  ```

### POST 요청 시 필수 필드
GET 응답의 `<form id="mainForm">` 에서 **모든 input 필드**를 추출해야 함:

| 필드명 | 설명 |
|---|---|
| `__VIEWSTATE` | ASP.NET 상태 (약 8000자) |
| `__VIEWSTATEGENERATOR` | 뷰스테이트 생성자 ID |
| `__EVENTVALIDATION` | 이벤트 유효성 검사 |
| `__EVENTTARGET` | 클릭된 버튼의 control ID |
| `__EVENTARGUMENT` | 이벤트 인자 (보통 빈 문자열) |
| `...hfPage` | 현재 페이지 번호 |
| `...hfOrderByCol` | 정렬 컬럼명 |
| `...hfOrderBy` | 정렬 방향 (ASC/DESC) |

### 가장 중요한 버그 주의사항

`__EVENTTARGET`을 설정할 때 **딕셔너리 병합 순서**에 주의:

```python
# ❌ 잘못된 방법 - **hidden이 마지막이라 __EVENTTARGET을 빈 문자열로 덮어씀
post_data = {
    "__EVENTTARGET": next_target,  # 여기서 설정해도
    **hidden,                       # hidden 안의 __EVENTTARGET="" 로 덮어씌워짐
}

# ✅ 올바른 방법 - hidden을 먼저 채운 뒤 덮어쓰기
hidden["__EVENTTARGET"] = next_target
hidden["__EVENTARGUMENT"] = ""
post_data = hidden
```

`__EVENTTARGET`이 빈 문자열로 전송되면 서버는 항상 **1페이지 데이터를 반환**하므로, 모든 페이지가 동일한 데이터로 수집되는 증상이 나타남.

---

## 세션 및 요청 설정

```python
session = requests.Session()  # 세션 재사용 필수 (쿠키 유지)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.koreabaseball.com",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
```

- 첫 요청은 **GET**, 페이지 이동은 **POST**
- 요청 사이에 `time.sleep(0.5)` 이상 딜레이 권장

---

## 테이블 파싱

- 메인 데이터 테이블: `class="tData"`
- BeautifulSoup 선택 우선순위:
  ```python
  table = (
      soup.find("table", class_="tData")
      or soup.select_one("div.record_wrap table")
      or soup.find("table")
  )
  ```

---

## 데이터 특성 주의사항

- **타자 기록**: 규정타석 충족 선수만 표시됨 (시즌 초반엔 64명 수준)
- **투수 기록**: 규정이닝 충족 선수만 표시됨 (시즌 초반엔 24명 수준)
- **수비 기록**: 한 선수가 여러 포지션을 소화했을 경우 포지션별로 **여러 행** 등록됨 (중복 아님, 원본 데이터 구조)
- **수비/주루**: KBO 사이트에 세부기록 탭 없음

---

## CSV 저장

```python
df.to_csv(filepath, index=False, encoding="utf-8-sig")
```

- `utf-8-sig` 사용 → Excel에서 한글 깨짐 없이 열림
