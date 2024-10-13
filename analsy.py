import streamlit as st
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
import folium
from streamlit_folium import folium_static
import numpy as np
import datetime
import random
import matplotlib.font_manager as fm
import os

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
            일련번호 TEXT,
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

# 데이터베이스에 데이터 저장
def save_to_database(df):
    conn = sqlite3.connect('vehicle_violations.db')
    df.to_sql('violations', conn, if_exists='append', index=False, chunksize=1000)
    conn.close()

# Streamlit 앱
st.title('차량단속 데이터 분석 대시보드')

# 데이터베이스 생성
create_database()

# 데이터 업로드
uploaded_file = st.file_uploader("엑셀 파일을 업로드하세요", type=["xlsx"], label_visibility="collapsed")
if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        # 파일 형식 검증
        required_columns = [
            "일련번호", "위반유형", "위반일시", "제한속도", "실제주행속도", "실제초과속도",
            "고지주행속도", "고지초과속도", "처리상태", "위반차로", "차종", "장소구분",
            "주민구분", "차명", "위반장소"
        ]
        if not all(col in df.columns for col in required_columns):
            st.error("업로드된 파일의 형식이 올바르지 않습니다. 올바른 형식의 파일을 업로드해주세요.")
        else:
            df_analysis = df[required_columns]
            # 개인정보 제거 후 데이터베이스에 저장
            save_to_database(df_analysis)
            st.success("파일이 데이터베이스에 저장되었습니다.")
    except Exception as e:
        st.error(f"파일을 처리하는 중 오류가 발생했습니다: {e}")

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
        st.sidebar.error("종료일을 선택하세요.")
        st.stop()
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
        st.experimental_rerun()

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

        # 단속 건수 표로 표시
        st.subheader('단속 건수 요약')
        total_count = df_selected['일련번호'].nunique()
        st.write(f'단속 건수 총합계: {total_count}건')
        summary = df_selected.groupby(['위반유형', '장소구분', '처리상태']).size().reset_index(name='건수')
        st.write(summary)
        st.write("카테고리 별 단속 건수 부분 합계:")
        part_sum = df_selected.groupby(['위반유형'])['일련번호'].nunique().reset_index(name='건수')
        st.write(part_sum)

        # 장비코드 검색 및 단속 건수 표시 (카테고리별 단속 건수 부분 합계 아래에 배치)
        st.header("장비코드 별 단속건수")
        equipment_code_input = st.text_input("장비코드를 입력하세요")
        if equipment_code_input:
            specific_equipment_data = df_selected[df_selected['장비코드'] == equipment_code_input]
            if not specific_equipment_data.empty:
                st.write(f"장비코드 {equipment_code_input}의 단속 장소 : {specific_equipment_data['위반장소'].iloc[0]}")
                total_daily_count = specific_equipment_data['일련번호'].nunique()  # 총합 계산
                st.write(f"장비코드 {equipment_code_input}의 일별 단속 건수 총합 : {total_daily_count}건")
                daily_counts = specific_equipment_data.groupby(specific_equipment_data['위반일시'].dt.date)['일련번호'].nunique().reset_index(name='단속 건수')
                daily_counts.columns = ['날짜', '단속 건수']
                daily_counts = daily_counts.set_index('날짜').T  # 가로 형태로 변환
                st.write(daily_counts)
                st.write(f"장비코드 {equipment_code_input}의 위반유형별 단속 건수:")
                violation_counts = specific_equipment_data.groupby('위반유형')['일련번호'].nunique().reset_index(name='단속 건수')
                st.write(violation_counts)

        # 장비코드별 단속 건수 상위 10개 시각화
        st.subheader('장비코드별 단속 건수 상위 10개')
        equipment_top10 = df_selected['장비코드'].value_counts().head(10)
        fig, ax = plt.subplots()
        ax.bar(equipment_top10.index, equipment_top10.values, color='skyblue')
        ax.set_xlabel('장비코드', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('장비코드별 단속 건수 (상위 10개)', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)
        st.pyplot(fig)

        # 단속 건수가 급증한 장비 경고 알림 (통계적 이상치 탐지)
        st.subheader('단속 건수 급증 경고')
        equipment_counts = df_db.groupby(['장비코드', df_db['위반일시'].dt.date]).size().unstack(fill_value=0)
        rolling_mean = equipment_counts.rolling(window=7, axis=1).mean()
        rolling_std = equipment_counts.rolling(window=7, axis=1).std()
        threshold = rolling_mean + (2 * rolling_std)  # 이동 평균 + 2표준편차를 이상치 기준으로 설정
        recent_counts = df_selected.groupby('장비코드').size()

        alerts = []
        for code in recent_counts.index:
            if code in threshold.columns and recent_counts[code] > threshold[code].iloc[-1]:
                alerts.append((code, recent_counts[code]))

        if alerts:
            st.warning("경고: 통계적 이상치가 발견된 단속 장비가 있습니다.")
            alert_df = pd.DataFrame(alerts, columns=['장비코드', '단속 건수'])
            st.write(alert_df)
            for code, count in alerts:
                st.write(f"장비코드 {code}에서 최근 단속 건수가 통계적 이상")

        # 위반 유형별 발생 빈도 시각화
        st.subheader('위반 유형별 발생 빈도')
        violation_counts = df_selected['위반유형'].value_counts()
        fig, ax = plt.subplots()
        ax.bar(violation_counts.index, violation_counts.values, color='skyblue')
        ax.set_xlabel('위반유형', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('위반 유형별 건수', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)
        st.pyplot(fig)

        # 시간대별 위반 건수 시각화
        df_selected['시간대'] = df_selected['위반일시'].dt.hour
        time_counts = df_selected['시간대'].value_counts().sort_index()
        st.subheader('시간대별 위반 건수')
        fig, ax = plt.subplots()
        ax.plot(time_counts.index, time_counts.values, marker='o', color='skyblue')
        ax.set_xlabel('시간대', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('시간대별 위반 건수', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)
        st.pyplot(fig)

        # 차종별 위반 건수 시각화
        st.subheader('차종별 위반 건수')
        car_type_counts = df_selected['차종'].value_counts()
        fig, ax = plt.subplots()
        ax.bar(car_type_counts.index, car_type_counts.values, color='skyblue')
        ax.set_xlabel('차종', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('차종별 건수', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)
        st.pyplot(fig)
        
# 데이터베이스 초기화 버튼 추가
def reset_database():
    conn = sqlite3.connect('vehicle_violations.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM violations')
    conn.commit()
    conn.close()

if st.sidebar.button("전체 DB 삭제"):
    reset_database()
    st.warning("전체 데이터베이스가 초기화되었습니다. 분석할 파일을 새로 업로드하세요.")
    st.experimental_rerun()
