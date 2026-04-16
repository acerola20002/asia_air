import json
import datetime
import re
from FlightRadar24 import FlightRadar24API

fr_api = FlightRadar24API()

# --- [기존 설정 유지] ---
# 국가별 핵심 공항 리스트 (국가당 최대 6개)
COUNTRY_AIRPORTS = {
    "일본": {"NRT": "나리타", "KIX": "간사이", "FUK": "후쿠오카", "CTS": "삿포로", "HND": "하네다", "OKA": "오키나와"},
    "베트남": {"CXR": "나트랑", "PQC": "푸꾸옥", "DAD": "다낭", "SGN": "호치민", "HAN": "하노이", "HPH": "하이퐁"},
    "태국": {"BKK": "방콕", "DMK": "돈무앙", "CNX": "치앙마이", "HKT": "푸켓", "USM": "코사무이", "UTP": "파타야"},
    "대만": {"TPE": "타오위안", "TSA": "송산", "KHH": "가오슝", "RMQ": "타이중", "HUN": "화롄", "MZG": "마궁"},
    "필리핀": {"MNL": "마닐라", "CEB": "세부", "MPH": "보라카이", "TAG": "보홀", "CRK": "클락", "PPS": "푸에르토프린세사"},
    "중국": {"PVG": "상하이", "PEK": "베이징", "TAO": "칭다오", "CAN": "광저우", "TNA": "제난", "SZX": "심천"}
}

# 기존 맵 데이터 그대로 유지
CITY_MAP = {
    "Incheon": "인천", "Busan": "부산", "Daegu": "대구", "Cheongju": "청주",
    "Muan": "무안", "Seoul": "서울", "Ho Chi Minh City": "호치민", "Hanoi": "하노이",
    "Nha Trang": "나트랑", "Da Nang": "다낭", "Kaohsiung": "가오슝", "Changi": "싱가포르",
    "Chengdu": "청두", "Macau": "마카오", "Hong Kong": "홍콩",
    "Shanghai": "상하이", "Taipei": "타이베이", "Bangkok": "방콕"
    # 일본 및 기타 도시 추가
    "Osaka": "오사카", "Tokyo": "도쿄", "Fukuoka": "후쿠오카", "Sapporo": "삿포로", "Nagoya": "나고야", "Okinawa": "오키나와"
}

IATA_MAP = {"MFM": "마카오", "HKG": "홍콩", "ICN": "인천", "PUS": "부산", "CXR": "나트랑/깜라인"}
DOMESTIC_CITIES = ["Ho Chi Minh City", "Hanoi", "Da Nang", "Dalat", "Hai Phong", "Dong Hoi", "Can Tho", "Phu Quoc", "Vinh", "Hue", "Tuy Hoa", "Qui Nhon", "Chu Lai"]

# --- [기존 함수 로직 그대로 유지] ---
def translate_status(raw_text):
    if not raw_text: return "정보없음"
    raw_text = re.sub(r'(dep|arr)\s*\d{2}:\d{2}', '', raw_text, flags=re.IGNORECASE).strip()
    time_match = re.search(r'\d{2}:\d{2}', raw_text)
    time_part = time_match.group() if time_match else ""
    if "Delayed" in raw_text: return f"지연 ({time_part})" if time_part else "지연"
    if "Estimated" in raw_text: return f"도착예정 ({time_part})" if time_part else "도착예정"
    if "Landed" in raw_text: return "도착완료"
    if "Scheduled" in raw_text: return "예정"
    return raw_text

def get_time_value(flight_info, mode):
    t_key = 'arrival' if mode == 'arrivals' else 'departure'
    time_data = flight_info.get('time', {})
    t_val = time_data.get('scheduled', {}).get(t_key)
    if not t_val: t_val = time_data.get('estimated', {}).get(t_key)
    return t_val

# --- [수정된 메인 업데이트 로직] ---
def update_data():
    try:
        # 전체 데이터를 담을 객체
        final_all_storage = {}
        
        # UTC 기준 현재 시간 (나중에 현지 시각 계산용으로 사용)
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # 국가별 순회
        for country_name, airport_list in COUNTRY_AIRPORTS.items():
            print(f"🌍 {country_name} 데이터 수집 시작...")
            country_storage = {}
            
            # 각 나라별 시차 설정 (베트남/태국 -2, 대만/필리핀/중국 -1, 일본 0)
            # 기준은 한국 시간이 아니라 계산의 편의를 위해 UTC 기반으로 나중에 처리
            
            for code, kor_name in airport_list.items():
                print(f"  📡 {kor_name}({code}) 수집 중...")
                raw_data = fr_api.get_airport_details(code) or {}
                schedule = raw_data.get('airport', {}).get('pluginData', {}).get('schedule', {})
                
                airport_storage = []

                for mode in ['arrivals', 'departures']:
                    data_list = schedule.get(mode, {}).get('data', [])
                    for f in data_list:
                        flight_info = f.get('flight', {})
                        if not flight_info: continue

                        port_type = 'origin' if mode == 'arrivals' else 'destination'
                        airport_data = flight_info.get('airport', {}).get(port_type, {})
                        iata_code = airport_data.get('code', {}).get('iata', '')
                        city_raw = airport_data.get('position', {}).get('region', {}).get('city', 'Unknown')
                        country_raw = airport_data.get('position', {}).get('country', {}).get('name', 'Unknown')

                        # 기존 필터 로직 그대로 유지
                        # --- [국내선 필터링 로직 강화] ---
                        # 1. 목적지/출발지 공항 코드가 현재 국가의 공항 리스트에 있으면 국내선
                        if iata_code in airport_list:
                            continue

                        # 2. 영문 국가명이 현재 수집 국가와 같으면 국내선
                        eng_countries = {"일본":"Japan", "베트남":"Vietnam", "태국":"Thailand", "대만":"Taiwan", "필리핀":"Philippines", "중국":"China"}
                        current_country_eng = eng_countries.get(country_name, "Unknown")
                        
                        if country_raw == current_country_eng or city_raw in DOMESTIC_CITIES:
                            continue
                        # --------------------------------

                        t_val = get_time_value(flight_info, mode)
                        if not t_val: continue

                        # 시간 처리: 1시간 전 데이터 필터링 로직 유지 (UTC 기준으로 계산)
                        f_time_utc = datetime.datetime.fromtimestamp(t_val, datetime.timezone.utc)
                        if f_time_utc < (now_utc - datetime.timedelta(hours=1)): continue

                        # 화면 표시용 시각 (가독성을 위해 UTC String으로 넘기고 JS에서 현지화하거나, 일단 기존처럼 저장)
                        # 여기서는 기존 구조 유지를 위해 그대로 둡니다.
                        date_str = f_time_utc.strftime('%m/%d %H:%M') 
                        raw_status = flight_info.get('status', {}).get('text', '')
                        kor_status = translate_status(raw_status)

                        # 출발 상태 세분화 로직 그대로 유지
                        if mode == 'departures':
                            diff_min = (f_time_utc - now_utc).total_seconds() / 60
                            if "지연" not in kor_status:
                                if diff_min <= 0: kor_status = "출발완료"
                                elif diff_min <= 15: kor_status = "탑승 곧 마감"
                                elif diff_min <= 45: kor_status = "탑승중"
                                else: kor_status = "출발예정"

                        # 도시 이름 한글화 로직 유지
                        display_city = CITY_MAP.get(city_raw, city_raw)
                        if iata_code == "MFM" or "Macau" in city_raw: display_city = "마카오"
                        elif iata_code == "HKG" or "Hong Kong" in city_raw: display_city = "홍콩"
                        elif iata_code in IATA_MAP: display_city = IATA_MAP[iata_code]

                        airport_storage.append({
                            "type": "도착" if mode == 'arrivals' else "출발",
                            "time": date_str,
                            "timestamp": t_val,
                            "flight": flight_info.get('identification', {}).get('number', {}).get('default', 'N/A'),
                            "city": display_city,
                            "status": kor_status
                        })
                
                country_storage[code] = sorted(airport_storage, key=lambda x: x['timestamp'])
            
            final_all_storage[country_name] = country_storage

        # 최종 저장 (JS 변수명은 기존 flightInfo 유지)
        final_output = {
            "lastUpdateUTC": now_utc.strftime('%Y-%m-%d %H:%M:%S'),
            "allData": final_all_storage
        }

        with open('data.js', 'w', encoding='utf-8') as f:
            f.write(f"const flightInfo = {json.dumps(final_output, ensure_ascii=False, indent=4)};")

        print(f"✅ 모든 국가 업데이트 성공 (UTC {now_utc.strftime('%H:%M')})")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    update_data()
