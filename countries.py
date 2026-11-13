"""소속 문자열 → 나라(한글 이름). 분석 탭의 '나라별' 비교에 쓴다.

PubMed 소속은 대개 '…, 도시, 나라' 모양이라 **뒤에서부터** 나라 이름을 찾는다. 미국은 나라 이름 없이
'Boston, MA 02115'처럼 주(州)만 적는 일이 많아 주 이름·약어도 미국으로 본다. 못 찾으면 빈 칸(화면은 '미상').
"""
import re

# 영어 표기(소문자, 여러 개) → 한글
COUNTRIES = {
    "미국": ["united states", "usa", "u.s.a", "u.s.", "us"],
    "영국": ["united kingdom", "uk", "england", "scotland", "wales", "northern ireland", "great britain"],
    "한국": ["republic of korea", "south korea", "korea"],
    "중국": ["china", "p.r. china", "pr china", "p. r. china", "p.r.china", "people's republic of china"],
    "홍콩": ["hong kong", "hong kong sar", "hong kong sar, china"],
    "대만": ["taiwan", "taiwan, roc", "republic of china"],
    "마카오": ["macau", "macao"],
    "일본": ["japan"],
    "싱가포르": ["singapore"],
    "캐나다": ["canada"],
    "호주": ["australia"],
    "뉴질랜드": ["new zealand"],
    "독일": ["germany"],
    "프랑스": ["france"],
    "네덜란드": ["the netherlands", "netherlands", "holland", "nl"],
    "벨기에": ["belgium"],
    "스위스": ["switzerland"],
    "오스트리아": ["austria"],
    "이탈리아": ["italy"],
    "스페인": ["spain"],
    "포르투갈": ["portugal"],
    "아일랜드": ["ireland"],
    "덴마크": ["denmark"],
    "스웨덴": ["sweden"],
    "노르웨이": ["norway"],
    "핀란드": ["finland"],
    "아이슬란드": ["iceland"],
    "폴란드": ["poland"],
    "체코": ["czech republic", "czechia"],
    "헝가리": ["hungary"],
    "그리스": ["greece"],
    "루마니아": ["romania"],
    "크로아티아": ["croatia"],
    "슬로베니아": ["slovenia"],
    "세르비아": ["serbia"],
    "에스토니아": ["estonia"],
    "리투아니아": ["lithuania"],
    "라트비아": ["latvia"],
    "우크라이나": ["ukraine"],
    "러시아": ["russia", "russian federation"],
    "튀르키예": ["turkey", "türkiye", "turkiye"],
    "이스라엘": ["israel"],
    "이란": ["iran", "islamic republic of iran"],
    "사우디아라비아": ["saudi arabia", "kingdom of saudi arabia"],
    "아랍에미리트": ["united arab emirates", "uae"],
    "카타르": ["qatar"],
    "요르단": ["jordan"],
    "레바논": ["lebanon"],
    "이집트": ["egypt"],
    "남아프리카공화국": ["south africa"],
    "나이지리아": ["nigeria"],
    "가나": ["ghana"],
    "케냐": ["kenya"],
    "에티오피아": ["ethiopia"],
    "우간다": ["uganda"],
    "탄자니아": ["tanzania"],
    "르완다": ["rwanda"],
    "말라위": ["malawi"],
    "인도": ["india"],
    "파키스탄": ["pakistan"],
    "방글라데시": ["bangladesh"],
    "네팔": ["nepal"],
    "스리랑카": ["sri lanka"],
    "태국": ["thailand"],
    "베트남": ["vietnam", "viet nam"],
    "말레이시아": ["malaysia"],
    "인도네시아": ["indonesia"],
    "필리핀": ["philippines"],
    "브라질": ["brazil"],
    "멕시코": ["mexico"],
    "칠레": ["chile"],
    "아르헨티나": ["argentina"],
    "콜롬비아": ["colombia"],
    "페루": ["peru"],
    "에콰도르": ["ecuador"],
    "쿠바": ["cuba"],
    "키프로스": ["cyprus"],
    "소말리아": ["somalia"],
    "모로코": ["morocco"],
    "튀니지": ["tunisia"],
    "카메룬": ["cameroon"],
    "짐바브웨": ["zimbabwe"],
    "잠비아": ["zambia"],
    "모잠비크": ["mozambique"],
    "보츠와나": ["botswana"],
    "오만": ["oman"],
    "쿠웨이트": ["kuwait"],
    "바레인": ["bahrain"],
    "이라크": ["iraq"],
    "카자흐스탄": ["kazakhstan"],
    "몽골": ["mongolia"],
    "캄보디아": ["cambodia"],
    "미얀마": ["myanmar"],
    "룩셈부르크": ["luxembourg"],
    "몰타": ["malta"],
    "불가리아": ["bulgaria"],
    "슬로바키아": ["slovakia"],
    "푸에르토리코": ["puerto rico"],
}
US_STATE_NAMES = {s.lower() for s in [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida",
    "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma",
    "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah",
    "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia"]}
# 'Georgia'는 나라 이름이기도 하지만 이 분야 저널에서는 거의 미국 주다
US_ABBR = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
              "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())

ALIAS = {}
for ko, names in COUNTRIES.items():
    for n in names:
        ALIAS[n] = ko


def country_of(aff):
    """소속 한 줄 → 한글 나라 이름, 모르면 ''."""
    if not aff:
        return ""
    a = re.sub(r"\S+@\S+", " ", aff)
    # 'Hong Kong SAR, China'처럼 뒤에 China가 붙어도 홍콩·마카오·대만은 따로 센다
    for name, ko in (("hong kong", "홍콩"), ("macau", "마카오"), ("macao", "마카오"), ("taiwan", "대만")):
        if name in a.lower():
            return ko
    a = re.sub(r"Electronic address:.*$", "", a, flags=re.I)
    parts = [p.strip(" .;") for p in re.split(r"[,;]", a) if p.strip(" .;")]
    for p in reversed(parts):
        low = re.sub(r"\s+", " ", p.lower())
        low = re.sub(r"\s*\d[\d -]*$", "", low).strip()        # 'Seoul 03722', 'Singapore 117549'
        low = re.sub(r"^\d[\d -]*\s*", "", low).strip()        # '10117 Berlin' 같은 앞 우편번호
        if low in ALIAS:
            return ALIAS[low]
        if low in US_STATE_NAMES:
            return "미국"
        m = re.fullmatch(r"([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?", p.strip())
        if m and m.group(1) in US_ABBR:
            return "미국"
    # 마지막 조각에 나라 이름이 붙어 있는 경우('Seoul, Korea.' 말고 'Seoul Korea') — 뒤쪽 단어로 다시 찾는다
    low = re.sub(r"[^a-z' .]", " ", a.lower())
    for n in sorted(ALIAS, key=len, reverse=True):
        if len(n) > 3 and re.search(rf"\b{re.escape(n)}\b\s*$", low.strip()):
            return ALIAS[n]
    return ""


# OpenAlex 기관 나라(ISO 2글자) → 한글. 소속에 나라 이름이 없는 논문('…, Shanghai Jiao Tong University')을 채울 때 쓴다
ISO = {"US": "미국", "GB": "영국", "KR": "한국", "CN": "중국", "HK": "홍콩", "TW": "대만", "MO": "마카오", "JP": "일본",
       "SG": "싱가포르", "CA": "캐나다", "AU": "호주", "NZ": "뉴질랜드", "DE": "독일", "FR": "프랑스", "NL": "네덜란드",
       "BE": "벨기에", "CH": "스위스", "AT": "오스트리아", "IT": "이탈리아", "ES": "스페인", "PT": "포르투갈", "IE": "아일랜드",
       "DK": "덴마크", "SE": "스웨덴", "NO": "노르웨이", "FI": "핀란드", "IS": "아이슬란드", "PL": "폴란드", "CZ": "체코",
       "HU": "헝가리", "GR": "그리스", "RO": "루마니아", "HR": "크로아티아", "SI": "슬로베니아", "RS": "세르비아",
       "EE": "에스토니아", "LT": "리투아니아", "LV": "라트비아", "UA": "우크라이나", "RU": "러시아", "TR": "튀르키예",
       "IL": "이스라엘", "IR": "이란", "SA": "사우디아라비아", "AE": "아랍에미리트", "QA": "카타르", "JO": "요르단",
       "LB": "레바논", "EG": "이집트", "ZA": "남아프리카공화국", "NG": "나이지리아", "GH": "가나", "KE": "케냐",
       "ET": "에티오피아", "UG": "우간다", "TZ": "탄자니아", "RW": "르완다", "MW": "말라위", "IN": "인도", "PK": "파키스탄",
       "BD": "방글라데시", "NP": "네팔", "LK": "스리랑카", "TH": "태국", "VN": "베트남", "MY": "말레이시아",
       "ID": "인도네시아", "PH": "필리핀", "BR": "브라질", "MX": "멕시코", "CL": "칠레", "AR": "아르헨티나",
       "CO": "콜롬비아", "PE": "페루", "EC": "에콰도르", "CU": "쿠바", "PR": "푸에르토리코", "CY": "키프로스",
       "SO": "소말리아", "MA": "모로코", "TN": "튀니지", "CM": "카메룬", "ZW": "짐바브웨", "ZM": "잠비아",
       "MZ": "모잠비크", "BW": "보츠와나", "OM": "오만", "KW": "쿠웨이트", "BH": "바레인", "IQ": "이라크",
       "KZ": "카자흐스탄", "MN": "몽골", "KH": "캄보디아", "MM": "미얀마", "LU": "룩셈부르크", "MT": "몰타",
       "BG": "불가리아", "SK": "슬로바키아"}
