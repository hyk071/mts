import streamlit as st
import requests
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import numpy as np
import datetime
import random
import os
import matplotlib.font_manager as fm
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

API_URL = "http://api.data.go.kr/openapi/tn_pubr_public_unmanned_traffic_camera_api"
SERVICE_KEY = "2ReGLeF8d8+JQrzLO3u3VGwVQ58Fi6mZVAogLJ3OBSmCTAfvjKs2dObu+juc2BSS4jdNlo1Q/o0du+b8z9SuKQ=="

# 한글 폰트 설정
font_path = os.path.join(os.getcwd(), 'static/fonts/NanumGothic.ttf')
font_prop = fm.FontProperties(fname=font_path)
plt.rcParams['font.family'] = font_prop.get_name()
plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지

# 데이터베이스 연결 및 테이블 생성
def create_database():
    conn = sqlite3.connect('vehicle_violations.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS violations (
            일련번호 TEXT PRIMARY KEY,
            위반유형 TEXT,
            위반일시 DATETIME,
            제한속도 INTEGER,
            실제주행속도 INTEGER,
            실제초과속도 INTEGER,
            고지주행속도 INTEGER,
            고지초과속도 INTEGER,
            처리상태 TEXT,
            위반차로 INTEGER,
            차종 TEXT,
            장소구분 TEXT,
            주민구분 TEXT,
            차명 TEXT,
            위반장소 TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 데이터베이스에 데이터 저장 (중복 확인 추가)
def save_to_database(df):
    conn = sqlite3.connect('vehicle_violations.db')
    cursor = conn.cursor()
    for _, row in df.iterrows():
        cursor.execute('''
            INSERT OR IGNORE INTO violations (일련번호, 위반유형, 위반일시, 제한속도, 실제주행속도, 실제초과속도, 고지주행속도, 고지초과속도, 처리상태, 위반차로, 차종, 장소구분, 주민구분, 차명, 위반장소)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            row['일련번호'], row['위반유형'], row['위반일시'], row['제한속도'], row['실제주행속도'], row['실제초과속도'],
            row['고지주행속도'], row['고지초과속도'], row['처리상태'], row['위반차로'], row['차종'], row['장소구분'],
            row['주민구분'], row['차명'], row['위반장소']
        ))
    conn.commit()
    conn.close()

# 시도명 자동 보정
def correct_region_name(input_name):
    region_mapping = {
        '서울': '서울특별시',
        '부산': '부산광역시',
        '울산': '울산광역시',
        '대전': '대전광역시',
        '대구': '대구광역시',
        '광주': '광주광역시',
        '인천': '인천광역시',
        '전라북도': '전북',
        '전라남도': '전남',
        '경상남도': '경남',
        '경상북도': '경북',
        '충청북도': '충북',
        '충청남도': '충남',
        '강원도': '강원',
        '경기도': '경기',
        # 필요에 따라 더 많은 지역 추가
    }
    return region_mapping.get(input_name, input_name)

# 카메라 데이터를 가져오는 함수
def get_camera_data(city=None, district=None, equipment_code=None):
    params = {
        'serviceKey': SERVICE_KEY,
        'numOfRows': 1000,
        'pageNo': 1,
        'type': 'json'
    }

    # 장비코드가 입력된 경우 해당 장비코드로 데이터 조회
    if equipment_code:
        params['mnlssRegltCameraManageNo'] = equipment_code
    else:
        # 시도명과 시군구명을 기준으로 데이터 조회
        if city:
            params['ctprvnNm'] = correct_region_name(city)
        if district:
            params['signguNm'] = district
    
    response = requests.get(API_URL, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if 'response' in data and 'body' in data['response'] and 'items' in data['response']['body']:
            return data['response']['body']['items']
        else:
            st.warning("해당 요청에 대한 데이터를 찾을 수 없습니다.")
            return []
    else:
        st.error("API 요청에 실패했습니다: " + response.text)
        return []

# 데이터베이스 초기화 버튼 추가
def reset_database():
    conn = sqlite3.connect('vehicle_violations.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM violations')
    conn.commit()
    conn.close()
    if 'equipment_code_input' in st.session_state:
        del st.session_state['equipment_code_input']
    st.warning("전체 데이터베이스가 초기화되었습니다. 분석할 파일을 새로 업로드하세요. 수동으로 새로고침 해주세요.")

# 이메일 알림 기능 추가
def send_email_alert(recipient_email, subject, body):
    sender_email = "your_email@example.com"
    sender_password = "your_password"
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.close()
        st.success("이메일 알림이 성공적으로 전송되었습니다.")
    except Exception as e:
        st.error(f"이메일 전송 실패: {e}")

# Streamlit 앱 시작
st.title("차량단속 데이터 분석 대시보드")

# 데이터베이스 생성
tab1, tab2 = st.tabs(["단속건수 분석", "단속장비 정보조회"])

# 단속건수 분석 탭
with tab1:
    st.header("단속건수 분석")
    uploaded_file = st.file_uploader("엑셀 파일 업로드", type=['xlsx'])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        save_to_database(df)
        st.success("데이터베이스에 저장되었습니다.")

    # 최근 분석 결과 표시
    conn = sqlite3.connect('vehicle_violations.db')
    df_db = pd.read_sql('SELECT * FROM violations', conn)
    conn.close()

    if not df_db.empty:
        # 장비코드 추가
        df_db['장비코드'] = df_db['일련번호'].str[:5]

        # 날짜 선택 위젯 추가
        st.sidebar.header("분석 결과 날짜 선택")
        df_db['위반일시'] = pd.to_datetime(df_db['위반일시'])
        available_dates = df_db['위반일시'].dt.date.unique()
        date_range = st.sidebar.date_input("기간 선택", value=(min(available_dates), max(available_dates)), min_value=min(available_dates), max_value=max(available_dates))
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date, end_date = min(available_dates), max(available_dates)
        df_selected = df_db[(df_db['위반일시'].dt.date >= start_date) & (df_db['위반일시'].dt.date <= end_date)]

        # 필터 추가
        st.sidebar.header("필터 설정")
        violation_type_filter = st.sidebar.selectbox("위반유형 선택", options=['전체'] + list(df_selected['위반유형'].unique()), index=0, key='violation_type_filter')
        status_filter = st.sidebar.selectbox("처리상태 선택", options=['전체'] + list(df_selected['처리상태'].unique()), index=0, key='status_filter')
        location_type_filter = st.sidebar.selectbox("장소구분 선택", options=['전체'] + list(df_selected['장소구분'].unique()), index=0, key='location_type_filter')

        # 필터 리셋 버튼 추가
        if st.sidebar.button("필터 리셋"):
            for key in ['violation_type_filter', 'status_filter', 'location_type_filter']:
                if key in st.session_state:
                    del st.session_state[key]
            st.warning("필터가 초기화되었습니다. 필요한 필터를 다시 선택하세요.")

        # 필터 적용
        if violation_type_filter != '전체':
            df_selected = df_selected[df_selected['위반유형'] == violation_type_filter]
        if status_filter != '전체':
            df_selected = df_selected[df_selected['처리상태'] == status_filter]
        if location_type_filter != '전체':
            df_selected = df_selected[df_selected['장소구분'] == location_type_filter]

        if not df_selected.empty:
            # 분석 결과 제목 표시
            start_date = df_selected['위반일시'].min().date()
            end_date = df_selected['위반일시'].max().date()
            st.subheader(f"분석 기간: {start_date} ~ {end_date}")

            # 단속 건수 및 위반유형별 건수 통합 표로 표시
            st.subheader('단속 건수 요약')
            daily_counts = df_selected.groupby(df_selected['위반일시'].dt.date)['일련번호'].nunique().reset_index(name='단속 건수')
            daily_counts.columns = ['날짜', '단속 건수']

            violation_counts = df_selected.groupby([df_selected['위반일시'].dt.date, '위반유형'])['일련번호'].nunique().unstack(fill_value=0)
            violation_counts.index.name = '날짜'

            combined_df = pd.concat([daily_counts.set_index('날짜').T, violation_counts.T], sort=False)
            combined_df = combined_df.loc[:, (combined_df != 0).any(axis=0)]  # 모든 건수가 0인 열 제거
            total_violations = df_selected['일련번호'].nunique()
            st.write(f'총 단속건수: {total_violations} 건')
            st.write(combined_df)

            # 데이터 다운로드 버튼 추가
            csv = df_selected.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="데이터 다운로드 (CSV)",
                data=csv,
                file_name='traffic_violation_data.csv',
                mime='text/csv'
            )

            # 장비코드 검색 및 단속 건수 표시 (통합 표로 변경)
            st.header("장비코드 별 단속건수")
            equipment_code_input = st.text_input("장비코드를 입력하세요 (예: F1234, G5678 등)", value="", key='equipment_code_input')
            if equipment_code_input:
                specific_equipment_data = df_selected[df_selected['장비코드'] == equipment_code_input]
                if not specific_equipment_data.empty:
                    st.write(f"장비코드 {equipment_code_input}의 단속 장소: {specific_equipment_data['위반장소'].iloc[0]}")
                    daily_counts = specific_equipment_data.groupby(specific_equipment_data['위반일시'].dt.date)['일련번호'].nunique().reset_index(name='단속 건수')
                    daily_counts.columns = ['날짜', '단속 건수']

                    violation_counts = specific_equipment_data.groupby([specific_equipment_data['위반일시'].dt.date, '위반유형'])['일련번호'].nunique().unstack(fill_value=0)
                    violation_counts.index.name = '날짜'

                    combined_df_specific = pd.concat([daily_counts.set_index('날짜').T, violation_counts.T], sort=False)
                    combined_df_specific = combined_df_specific.loc[:, (combined_df_specific != 0).any(axis=0)]  # 모든 건수가 0인 열 제거
                    total_specific_violations = specific_equipment_data['일련번호'].nunique()
                    st.write(f'총 단속건수: {total_specific_violations} 건')
                    st.write(combined_df_specific)

                    # 이메일 알림 발송 옵션 추가
                    recipient_email = st.text_input("이메일 주소를 입력하세요 (알림 전송용)")
                    if st.button("이메일 알림 발송"):
                        if recipient_email:
                            subject = f"장비코드 {equipment_code_input}의 단속 건수 통계"
                            body = combined_df_specific.to_string()
                            send_email_alert(recipient_email, subject, body)
                        else:
                            st.error("이메일 주소를 입력해주세요.")

# 단속장비 정보조회 탭
with tab2:
    st.header("무인 교통 단속 카메라 정보조회")
    # 장비코드를 입력받아 해당 정보를 조회하는 폼 추가
    option = st.radio("조회 옵션을 선택하세요", ('장비코드로 조회', '시도명/시군구명으로 조회'))
    if option == '장비코드로 조회':
        equipment_code_input = st.text_input("장비코드를 입력하세요 (예: F1234, G5678 등)", key='equipment_code_lookup')
        if equipment_code_input:
            pattern = r'^[F-J][0-9]{4}$'
            if re.match(pattern, equipment_code_input):
                specific_camera_data = get_camera_data(equipment_code=equipment_code_input)
                if specific_camera_data:
                    st.write(f"장비코드 {equipment_code_input}의 카메라 데이터:")
                    st.dataframe(pd.DataFrame(specific_camera_data))
                else:
                    st.write(f"장비코드 {equipment_code_input}에 해당하는 카메라 정보가 없습니다.")
            else:
                st.error("올바른 장비코드를 입력해주세요 (알파벳 F-J, 숫자 0000-9999 형식)")
    elif option == '시도명/시군구명으로 조회':
        # 시도명과 시군구명 입력 필드 추가
        city = st.text_input("시도명을 입력하세요 (예: 서울, 경상남도 등)", "서울특별시")
        district = st.text_input("시군구명을 입력하세요 (예: 강남구, 창원시 등)")

        # 사용자가 버튼을 눌러 데이터를 가져옴
        if st.button("카메라 데이터 가져오기"):
            camera_data = get_camera_data(city=city, district=district)
            st.session_state['camera_data'] = camera_data

    # 세션 상태에 데이터가 있는 경우 표시
    if 'camera_data' in st.session_state and st.session_state['camera_data'] and option == '시도명/시군구명으로 조회':
        df = pd.DataFrame(st.session_state['camera_data'])
        st.write(f"{city} {district}의 카메라 데이터:")
        st.dataframe(df)

        # 지도 생성
        if not df.empty:
            center_lat = df['latitude'].astype(float).mean()
            center_lon = df['longitude'].astype(float).mean()

            # Folium 지도 객체 생성
            folium_map = folium.Map(location=[center_lat, center_lon], zoom_start=12)

            # 카메라 위치를 지도에 추가
            for idx, row in df.iterrows():
                folium.Marker([float(row['latitude']), float(row['longitude'])],
                              popup=f"단속구분: {row['regltSe']}<br>장소: {row['itlpc']}<br>제한속도: {row['lmttVe']}km/h").add_to(folium_map)

            # Streamlit에 Folium 지도 표시
            st_folium(folium_map)

# 데이터베이스 초기화 버튼
if st.sidebar.button("전체 DB 삭제"):
    reset_database()
    st.warning("전체 데이터베이스가 초기화되었습니다. 수동으로 새로고침 해주세요.")
