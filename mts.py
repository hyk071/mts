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
        '전라북도': '전라북도',
        '전라남도': '전라남도',
        '경상남도': '경상남도',
        '경상북도': '경상북도',
        '충청북도': '충청북도',
        '충청남도': '충청남도',
        '강원도': '강원도',
        '경기도': '경기도',
        # 필요에 따라 더 많은 지역 추가
    }
    return region_mapping.get(input_name, input_name)

# 카메라 데이터를 가져오는 함수
def get_camera_data(city, district=None):
    params = {
        'serviceKey': SERVICE_KEY,
        'numOfRows': 1000,
        'pageNo': 1,
        'type': 'json',
        'ctprvnNm': correct_region_name(city),
    }
    
    if district:
        params['signguNm'] = district
    
    response = requests.get(API_URL, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if 'response' in data and 'body' in data['response'] and 'items' in data['response']['body']:
            # 데이터 필터링: 단속구분이 1 또는 2인 항목만 선택
            filtered_cameras = [
                camera for camera in data['response']['body']['items'] 
                if camera.get('regltSe') in ['1', '2']
            ]
            return filtered_cameras
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

# Streamlit 앱 시작
st.title("단속 건수 및 무인 교통 단속 카메라 위치 시각화")

# 데이터베이스 생성
tab1, tab2 = st.tabs(["단속건수 분석", "단속장비 시각화"])

# 단속건수 분석 탭
with tab1:
    st.header("단속건수 분석")
    uploaded_file = st.file_uploader("엑셀 파일 업로드", type=['xlsx'])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        save_to_database(df)
        st.success("데이터베이스에 저장되었습니다.")
        
        # 분석 작업
        conn = sqlite3.connect('vehicle_violations.db')
        query = "SELECT * FROM violations"
        df_selected = pd.read_sql(query, conn)
        conn.close()
        
        # 위반유형별 건수 시각화
        st.subheader("위반유형별 단속건수")
        violation_counts = df_selected['위반유형'].value_counts()
        fig, ax = plt.subplots()
        bars = ax.bar(violation_counts.index, violation_counts.values, color='skyblue')
        ax.set_xlabel('위반유형', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('위반유형별 단속건수', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)

        # 그래프에 마우스를 올렸을 때 건수 표시
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{bar.get_height()}', ha='center', va='bottom', fontproperties=font_prop)
        st.pyplot(fig)

        # 시간대별 위반 건수 시각화
        st.subheader("시간대별 단속건수")
        df_selected['위반일시'] = pd.to_datetime(df_selected['위반일시'])
        df_selected['시간대'] = df_selected['위반일시'].dt.hour
        time_counts = df_selected['시간대'].value_counts().sort_index()
        fig, ax = plt.subplots()
        line, = ax.plot(time_counts.index, time_counts.values, marker='o', color='skyblue')
        ax.set_xlabel('시간대', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('시간대별 단속건수', fontproperties=font_prop)
        ax.set_xticks(range(0, 24, 1))
        ax.set_yticks(range(0, max(time_counts.values) + 10, 10))
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)

        # 그래프에 마우스를 올렸을 때 건수 표시
        for i, txt in enumerate(time_counts.values):
            ax.text(time_counts.index[i], time_counts.values[i], f'{txt}', ha='center', va='bottom', fontproperties=font_prop)
        st.pyplot(fig)

        # 차종별 위반 건수 시각화
        st.subheader("차종별 단속건수")
        car_type_counts = df_selected['차종'].value_counts()
        fig, ax = plt.subplots()
        bars = ax.bar(car_type_counts.index, car_type_counts.values, color='skyblue')
        ax.set_xlabel('차종', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('차종별 단속건수', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)

        # 그래프에 마우스를 올렸을 때 건수 표시
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{bar.get_height()}', ha='center', va='bottom', fontproperties=font_prop)
        st.pyplot(fig)

# 단속장비 시각화 탭
with tab2:
    st.header("무인 교통 단속 카메라 위치 시각화")
    # 사용자가 시도명과 시군구명을 입력할 수 있도록 텍스트 입력 필드 추가
    city = st.text_input("시도명을 입력하세요 (예: 서울, 경상남도 등)", "서울특별시")
    district = st.text_input("시군구명을 입력하세요 (예: 강남구, 창원시 등)")

    # 사용자가 버튼을 눌러 데이터를 가져옴
    if st.button("카메라 데이터 가져오기"):
        camera_data = get_camera_data(city, district)
        st.session_state['camera_data'] = camera_data

    # 세션 상태에 데이터가 있는 경우 표시
    if 'camera_data' in st.session_state and st.session_state['camera_data']:
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

        # 제한속도 분석
        st.write("### 제한속도 분석")
        if 'lmttVe' in df.columns:
            speed_limit_counts = df['lmttVe'].value_counts().sort_index()
            st.bar_chart(speed_limit_counts)
        else:
            st.write("제한속도 데이터가 없습니다.")
    else:
        st.write("해당 지역에 대한 데이터를 찾을 수 없습니다.")

# 데이터베이스 초기화 버튼
if st.sidebar.button("전체 DB 삭제"):
    reset_database()
    st.warning("전체 데이터베이스가 초기화되었습니다. 분석할 파일을 새로 업로드하세요.")
    st.experimental_rerun()