import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.cloud import bigquery
from google.oauth2.credentials import Credentials
import os

st.set_page_config(page_title="Citi Bike 2026 Ridership", layout="wide")
st.title("Citi Bike 2026 Ridership Dashboard")

PROJECT_ID = "project-4dbffca4-5d78-4e9e-b64"


@st.cache_resource
def get_client():
    token = os.environ.get("GCP_TOKEN")
    if token:
        creds = Credentials(token=token)
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    # Falls back to Application Default Credentials in Cloud Run
    return bigquery.Client(project=PROJECT_ID)


@st.cache_data(ttl=3600)
def query(sql):
    client = get_client()
    return client.query(sql).to_dataframe()


# --- Daily ridership ---
daily_df = query("""
    SELECT
        DATE(started_at) AS ride_date,
        COUNT(*) AS rides,
        COUNTIF(member_casual = 'member') AS member_rides,
        COUNTIF(member_casual = 'casual') AS casual_rides
    FROM `project-4dbffca4-5d78-4e9e-b64.citibike.trips_2026`
    GROUP BY ride_date
    ORDER BY ride_date
""")

# --- Hourly pattern ---
hourly_df = query("""
    SELECT
        EXTRACT(HOUR FROM started_at) AS hour,
        EXTRACT(DAYOFWEEK FROM started_at) AS dow,
        COUNT(*) AS rides
    FROM `project-4dbffca4-5d78-4e9e-b64.citibike.trips_2026`
    GROUP BY hour, dow
    ORDER BY hour, dow
""")

# --- Bike type breakdown ---
type_df = query("""
    SELECT
        rideable_type,
        COUNT(*) AS rides
    FROM `project-4dbffca4-5d78-4e9e-b64.citibike.trips_2026`
    GROUP BY rideable_type
""")

# --- Top stations ---
station_df = query("""
    SELECT
        start_station_name AS station,
        COUNT(*) AS departures
    FROM `project-4dbffca4-5d78-4e9e-b64.citibike.trips_2026`
    WHERE start_station_name IS NOT NULL AND start_station_name != ''
    GROUP BY station
    ORDER BY departures DESC
    LIMIT 20
""")

# --- KPI row ---
total = daily_df["rides"].sum()
avg_daily = int(daily_df["rides"].mean())
peak_day = daily_df.loc[daily_df["rides"].idxmax(), "ride_date"]

col1, col2, col3 = st.columns(3)
col1.metric("Total Rides (2026)", f"{total:,}")
col2.metric("Avg Daily Rides", f"{avg_daily:,}")
col3.metric("Peak Day", str(peak_day))

st.divider()

# --- Daily ridership over time ---
st.subheader("Daily Ridership Over Time")
fig_daily = px.line(
    daily_df, x="ride_date", y=["member_rides", "casual_rides"],
    labels={"value": "Rides", "ride_date": "Date", "variable": "Rider Type"},
    color_discrete_map={"member_rides": "#1f77b4", "casual_rides": "#ff7f0e"},
)
fig_daily.update_layout(legend_title_text="Rider Type", hovermode="x unified")
st.plotly_chart(fig_daily, use_container_width=True)

# --- Hourly heatmap + bike type ---
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Rides by Hour & Day of Week")
    dow_labels = {1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat"}
    hourly_df["day"] = hourly_df["dow"].map(dow_labels)
    pivot = hourly_df.pivot(index="hour", columns="day", values="rides").fillna(0)
    pivot = pivot[[c for c in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] if c in pivot.columns]]
    fig_heat = px.imshow(
        pivot, aspect="auto", color_continuous_scale="Blues",
        labels={"x": "Day", "y": "Hour", "color": "Rides"},
    )
    st.plotly_chart(fig_heat, use_container_width=True)

with col_right:
    st.subheader("Bike Type")
    fig_pie = px.pie(type_df, names="rideable_type", values="rides", hole=0.4)
    st.plotly_chart(fig_pie, use_container_width=True)

# --- Top stations ---
st.subheader("Top 20 Departure Stations")
fig_bar = px.bar(
    station_df.sort_values("departures"), x="departures", y="station",
    orientation="h", labels={"departures": "Departures", "station": ""},
    color="departures", color_continuous_scale="Blues",
)
fig_bar.update_layout(showlegend=False, coloraxis_showscale=False, height=550)
st.plotly_chart(fig_bar, use_container_width=True)
