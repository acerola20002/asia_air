import json
import datetime
import re
from FlightRadar24 import FlightRadar24API

fr_api = FlightRadar24API()

# 대상 공항 리스트 (6개)
TARGET_AIRPORTS = {
    "CXR": "나트랑",
    "PQC": "푸꾸옥",
    "DAD": "다낭",
    "SGN": "호치민",
    "HAN": "하노이",
    "HPH": "하이퐁"
}

CITY_MAP = {
    "Incheon": "인천", "Busan": "부산", "Daegu": "대구", "Cheongju": "청주",
    "Muan": "무안", "Seoul": "서울", "Ho Chi Minh City": "호치민", "Hanoi": "하노이",
    "Nha Trang": "나트랑", "Da Nang": "다낭", "Kaohsiung": "가오슝", "Changi": "싱가포르",
    "Chengdu": "청두", "Macau": "마카오", "Hong Kong": "홍콩",
    "Shanghai": "상하이", "Taipei": "타이베이", "Bangkok": "방콕"
}

IATA_MAP = {
    "MFM": "마카오", "HKG": "홍콩", "ICN": "인천", "PUS": "부산", "CXR": "나트랑/깜라인"
}

DOMESTIC_CITIES = [
    "Ho Chi Minh City", "Hanoi", "Da Nang", "Dalat", "Hai Phong", "Dong Hoi",
    "Can Tho", "Phu Quoc", "Vinh", "Hue", "Tuy Hoa", "Qui Nhon", "Chu Lai"
]

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

def update_data():
    try:
        now_vn = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
        now_vn_naive = now_vn.replace(tzinfo=None)
        
        all_storage = {} # 6개 공항 데이터를 담을 그릇

        for code, kor_name in TARGET_AIRPORTS.items():
            print(f"📡 {kor_name}({code}) 데이터 수집 중...")
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
                    # 국가 정보 추가
                    country_raw = airport_data.get('position', {}).get('country', {}).get('name', 'Unknown')

                    # [통합 필터 로직] 
                    # 1. 국가가 베트남(Vietnam)이면 무조건 제외 (가장 확실함)
                    # 2. 혹은 IATA 코드가 우리가 관리하는 베트남 6개 공항 리스트에 있으면 제외
                    # 3. 혹은 도시 이름이 DOMESTIC_CITIES 리스트에 있으면 제외
                    if country_raw == "Vietnam" or iata_code in TARGET_AIRPORTS or city_raw in DOMESTIC_CITIES:
                        continue

                    # --- 위 필터를 통과한 '진짜 국제선'만 아래 로직을 탑니다 ---
                    display_city = CITY_MAP.get(city_raw, city_raw)
                    if iata_code == "MFM" or "Macau" in city_raw: display_city = "마카오"
                    elif iata_code == "HKG" or "Hong Kong" in city_raw: display_city = "홍콩"
                    elif iata_code in IATA_MAP: display_city = IATA_MAP[iata_code]

                    t_val = get_time_value(flight_info, mode)
                    if not t_val: continue
                    # 위 필터를 통과했다면 이제 '외국' 공항만 남았습니다.
                    display_city = CITY_MAP.get(city_raw, city_raw)
                    # ... 이후 한글 변환 로직 그대로 유지
                   
                    # 1. 도시 이름이 국내선 리스트에 있거나
                    # 2. 출발(departures)인데 목적지 IATA 코드가 우리가 관리하는 베트남 공항이면 제외
                    if city_raw in DOMESTIC_CITIES or (mode == 'departures' and iata_code in TARGET_AIRPORTS):
                        continue
                    # ---------------------------------------

                    display_city = CITY_MAP.get(city_raw, city_raw)
                    if iata_code == "MFM" or "Macau" in city_raw: display_city = "마카오"
                    elif iata_code == "HKG" or "Hong Kong" in city_raw: display_city = "홍콩"
                    elif iata_code in IATA_MAP: display_city = IATA_MAP[iata_code]

                    t_val = get_time_value(flight_info, mode)
                    if not t_val: continue

                    f_time_vn = datetime.datetime.fromtimestamp(t_val, datetime.timezone.utc) + datetime.timedelta(hours=7)
                    f_time_vn_naive = f_time_vn.replace(tzinfo=None)

                    # 1시간 전 데이터부터만 유지
                    if f_time_vn_naive < (now_vn_naive - datetime.timedelta(hours=1)): continue

                    date_str = f_time_vn_naive.strftime('%m/%d %H:%M')
                    raw_status = flight_info.get('status', {}).get('text', '')

                    # 이렇게 하면 '지연' 정보가 기본적으로 kor_status에 담깁니다.
                    kor_status = translate_status(raw_status)

                    # 2. 만약 출발(departures) 모드라면, 시간에 따라 상태를 더 세분화합니다.
                    if mode == 'departures':
                        diff_min = (f_time_vn_naive - now_vn_naive).total_seconds() / 60
                        
                        # 지연 정보가 없을 때만 시간 기반 상태(탑승중 등)를 보여줍니다.
                        # 만약 지연 정보가 있다면 '지연' 상태를 유지하는 게 안전합니다.
                        if "지연" not in kor_status:
                            if diff_min <= 0: 
                                kor_status = "출발완료"
                            elif diff_min <= 15: 
                                kor_status = "탑승 곧 마감"
                            elif diff_min <= 45: 
                                kor_status = "탑승중"
                            else: 
                                kor_status = "출발예정"
                    
                    # 3. 도착(arrivals)은 위에서 만든 kor_status를 그대로 사용하게 됩니다.
                    # (별도의 if문이 없으므로 자연스럽게 translate_status 결과값이 유지됨)

                    airport_storage.append({
                        "type": "도착" if mode == 'arrivals' else "출발",
                        "time": date_str,
                        "timestamp": t_val,
                        "flight": flight_info.get('identification', {}).get('number', {}).get('default', 'N/A'),
                        "city": display_city,
                        "status": kor_status
                    })
            
            # 시간순 정렬 후 저장
            all_storage[code] = sorted(airport_storage, key=lambda x: x['timestamp'])

        # 최종 저장 구조
        final_output = {
            "lastUpdate": now_vn.strftime('%Y-%m-%d %H:%M:%S'),
            "allData": all_storage
        }

        with open('data.js', 'w', encoding='utf-8') as f:
            f.write(f"const flightInfo = {json.dumps(final_output, ensure_ascii=False, indent=4)};")

        print(f"✅ 모든 공항 업데이트 성공: {now_vn.strftime('%Y-%m-%d %H:%M')}")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    update_data()
