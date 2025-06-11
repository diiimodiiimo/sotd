import streamlit as st
import pandas as pd
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from datetime import datetime


import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe


# Set Page Config - Must be FIRST
st.set_page_config(page_title="Dimo's Songs of the Day", layout="wide", initial_sidebar_state="collapsed")


# CSS Styling
st.markdown(
    """
    <style>
        :root {
            --primary: #E6B800;
            --bg: #000000;
            --card: #1e1e1e;
            --warn-bg: #5c1d1d;
            --warn-text: #ffffff;
        }
        .stApp { background-color: var(--bg) !important; font-family: 'Segoe UI', sans-serif; }
        .block-container { padding: 2rem 2rem; }
        h1, h2, h3, h4, h5, h6, label, p, span, div, .stMarkdown { color: var(--primary) !important; }
        .stButton>button { background-color: var(--card) !important; color: var(--primary) !important; border-radius: 5px; font-weight: bold; }
        .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"], .stDateInput input {
            background-color: var(--card) !important; color: var(--primary) !important; border: 1px solid var(--primary) !important;
        }
        .stSelectbox > div > div, div[data-baseweb="calendar"], div[role="option"], .stSlider {
            background-color: var(--card) !important; color: var(--primary) !important;
        }
        th, td, .stDataFrame th, .stDataFrame td {
            background-color: var(--card) !important; color: var(--primary) !important;
        }
        .stWarning { background-color: var(--warn-bg) !important; color: var(--warn-text) !important; border-left: 0.5rem solid #ff4d4d !important; }
    </style>
    """,
    unsafe_allow_html=True
)


# App Title
st.title("Dimo's Songs of the Day")


# Spotify Secrets
SPOTIPY_CLIENT_ID = st.secrets["SPOTIPY_CLIENT_ID"]
SPOTIPY_CLIENT_SECRET = st.secrets["SPOTIPY_CLIENT_SECRET"]
SPOTIPY_REDIRECT_URI = st.secrets["SPOTIPY_REDIRECT_URI"]
PLAYLIST_ID = st.secrets["PLAYLIST_ID"]


# Authenticate with Spotify
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope="playlist-read-private,playlist-modify-public,playlist-modify-private"
))


# Load from Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
import json
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(st.secrets["GOOGLE_CREDENTIALS"]),
    scope
)

client = gspread.authorize(creds)
sheet = client.open("sotd").sheet1
sotd_df_stream = get_as_dataframe(sheet).dropna(how="all")


# Semester Mapping
def assign_semester(date):
    year = date.year
    month = date.month
    if 1 <= month <= 5: return f"{year} - Jan–May"
    elif 6 <= month <= 8: return f"{year} - June–Aug"
    else: return f"{year} - Aug–Dec"


sotd_df_stream["Date"] = pd.to_datetime(sotd_df_stream["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
sotd_df_stream["Semester"] = pd.to_datetime(sotd_df_stream["Date"], errors="coerce").apply(assign_semester)
sorted_semesters = sorted(sotd_df_stream["Semester"].dropna().unique(), key=lambda x: (int(x.split(" - ")[0]), x.split(" - ")[1]))


st.title("How will we remember the day?")
tabs = st.tabs(["📅 Add New Entry", "📊 Analytics", "📜 Historically Today", "📅 Full Daily History"])


# Tab 1: Add New Entry
with tabs[0]:
    st.subheader("➕ Add a New Song of the Day")
    date = st.date_input("Select a Date", key="date_picker")
    if date:
        date_str = date.strftime("%Y-%m-%d")
        existing_entry = sotd_df_stream[sotd_df_stream["Date"] == date_str]
        if not existing_entry.empty:
            song_title = existing_entry.iloc[0]["Song Title"]
            artist = existing_entry.iloc[0]["Artist"]
            st.success(f"✅ A song already exists for {date_str}: **{song_title}** by **{artist}**")
            if st.button("Would you like to overwrite it?"):
                sotd_df_stream = sotd_df_stream[sotd_df_stream["Date"] != date_str]
                set_with_dataframe(sheet, sotd_df_stream)
                st.warning(f"⚠️ The existing entry for {date_str} has been removed. You can now add a new song.")
        else:
            st.markdown(f"<span style='color:#FF4D4D; font-weight:bold;'>🔴 No song exists for {date_str}. Please add a song.</span>", unsafe_allow_html=True)
            query = st.text_input("Search for a Song on Spotify", key="song_search")
            if query:
                results = sp.search(q=query, limit=5, type="track")
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    track_options = {f"{track['name']} - {track['artists'][0]['name']}": track for track in tracks}
                    selected_track = st.radio("Select a Song", list(track_options.keys()), key="track_selection")
                    if selected_track:
                        track_data = track_options[selected_track]
                        st.image(track_data["album"]["images"][0]["url"], caption="Album Art", width=200)
                        if st.button("Check if in Playlist"):
                            with st.spinner("Checking..."):
                                playlist_tracks = sp.playlist_tracks(PLAYLIST_ID)
                                in_playlist = any(item["track"]["id"] == track_data["id"] for item in playlist_tracks["items"])
                            if in_playlist:
                                st.success("✅ This song is already in the playlist!")
                            else:
                                st.warning("⚠️ This song is NOT in the playlist.")
                            if st.button("Add to Playlist"):
                                sp.playlist_add_items(PLAYLIST_ID, [track_data["uri"]])
                                st.success("🎶 Song added to playlist!")


                        notes = st.text_area("Enter Notes for the Day", key="notes_input")
                        if st.button("Save to SOTD"):
                            new_entry = {
                                "Date": date_str,
                                "Song Title": track_data["name"],
                                "Artist": track_data["artists"][0]["name"],
                                "Album Title": track_data["album"]["name"],
                                "Album Art": track_data["album"]["images"][0]["url"],
                                "Duration (ms)": track_data["duration_ms"],
                                "Explicit": "Yes" if track_data["explicit"] else "No",
                                "Popularity": track_data["popularity"],
                                "Release Date": track_data["album"]["release_date"],
                                "ID": sotd_df_stream["ID"].astype(float).max() + 1 if sotd_df_stream["ID"].notna().any() else 1,
                                "Track ID": track_data["id"],
                                "URI": track_data["uri"],
                                "Notes": notes
                            }
                            sotd_df_stream = pd.concat([sotd_df_stream, pd.DataFrame([new_entry])], ignore_index=True)
                            set_with_dataframe(sheet, sotd_df_stream)
                            st.success(f"🎵 {track_data['name']} by {track_data['artists'][0]['name']} added successfully!")


# Tabs 2–4 would follow here as usual (Analytics, Historically Today, Full Daily History) — and still use `sotd_df_stream`!



# **Tab 2: Analytics**
with tabs[1]:
    st.subheader("📊 Top Artists & Songs")

    # Convert to datetime
    sotd_df_stream["Date_dt"] = pd.to_datetime(sotd_df_stream["Date"], errors="coerce")
    sotd_df_stream["Semester"] = pd.to_datetime(sotd_df_stream["Date"], errors="coerce").apply(assign_semester)
    today = datetime.today()

    # Filter Mode + Layout
    col1, col2 = st.columns([1, 2])
    with col1:
        filter_option = st.radio("Choose Filter Mode:", ["Last 4 Weeks", "Last 6 Months", "Calendar Year", "Custom Range"])
    with col2:
        if filter_option == "Calendar Year":
            year_selected = st.selectbox(
                "Select Year",
                sorted(sotd_df_stream["Date_dt"].dt.year.dropna().unique(), reverse=True),
                index=0
            )

    # Apply date filter
    if filter_option == "Last 4 Weeks":
        start = today - pd.Timedelta(weeks=4)
        filtered_df = sotd_df_stream[sotd_df_stream["Date_dt"] >= start]
    elif filter_option == "Last 6 Months":
        start = today - pd.DateOffset(months=6)
        filtered_df = sotd_df_stream[sotd_df_stream["Date_dt"] >= start]
    elif filter_option == "Calendar Year":
        filtered_df = sotd_df_stream[sotd_df_stream["Date_dt"].dt.year == year_selected]
    else:
        min_date = sotd_df_stream["Date_dt"].min().date()
        max_date = sotd_df_stream["Date_dt"].max().date()
        start_date, end_date = st.slider("Select Custom Range:", min_value=min_date, max_value=max_date, value=(min_date, max_date))
        filtered_df = sotd_df_stream[
            (sotd_df_stream["Date_dt"].dt.date >= start_date) & 
            (sotd_df_stream["Date_dt"].dt.date <= end_date)
        ]

    # Semester filtering
    semester_options = sorted(filtered_df["Semester"].dropna().unique())
    selected_semester = st.selectbox("Filter by Semester:", ["All Semesters"] + semester_options)

    if selected_semester != "All Semesters":
        filtered_df = filtered_df[filtered_df["Semester"] == selected_semester]

    # Top Artists & Songs
    full_top_artists = filtered_df["Artist"].value_counts().head(10)
    top_artists = full_top_artists.head(3)
    top_songs = filtered_df.groupby(["Song Title", "Artist"]).size().reset_index(name="Count").sort_values(by="Count", ascending=False)
    top_songs_podium = top_songs.head(3)

    st.markdown("### 🏆 Top Artists Podium")
    top_artists_df = top_artists.reset_index()
    top_artists_df.columns = ['Artist', 'Count']
    cols = st.columns(3)

    for i, col in enumerate(cols):
        if i >= len(top_artists_df): break
        artist_name = top_artists_df.loc[i, "Artist"]
        count = top_artists_df.loc[i, "Count"]
        try:
            artist_result = sp.search(q=f"artist:{artist_name}", type='artist', limit=1)
            artist_image = artist_result['artists']['items'][0]['images'][0]['url']
        except:
            artist_image = "https://via.placeholder.com/150"
        with col:
            st.image(artist_image, width=150)
            st.markdown(f"### {['🥇','🥈','🥉'][i]}")
            st.markdown(f"**{artist_name}**")
            st.markdown(f"🎧 {count} time(s)")

    if st.checkbox("Show Full Top 10 Artists Table"):
        st.table(full_top_artists.reset_index().rename(columns={"index": "Artist", "Artist": "Count"}))

    st.markdown("---")
    st.markdown("### 🎵 Top Songs Podium")
    top_songs_df = top_songs_podium.reset_index(drop=True)
    cols = st.columns(3)

    for i, col in enumerate(cols):
        if i >= len(top_songs_df): break
        song = top_songs_df.loc[i, "Song Title"]
        artist = top_songs_df.loc[i, "Artist"]
        count = top_songs_df.loc[i, "Count"]
        try:
            track_result = sp.search(q=f"track:{song} artist:{artist}", type='track', limit=1)
            song_image = track_result['tracks']['items'][0]['album']['images'][0]['url']
        except:
            song_image = "https://via.placeholder.com/150"
        with col:
            st.image(song_image, width=150)
            st.markdown(f"### {['🥇','🥈','🥉'][i]}")
            st.markdown(f"**{song}**")
            st.markdown(f"*by {artist}*")
            st.markdown(f"🗓️ {count} time(s)")

    if st.checkbox("Show Full Top 10 Songs Table"):
        st.table(top_songs.head(10).reset_index(drop=True))

    # Artist Search
    st.markdown("---")
    st.subheader("🔍 Search by Artist")
    artist_query = st.text_input("Search for an artist:", key="artist_search")
    if artist_query:
        artist_matches = filtered_df[filtered_df["Artist"].str.contains(artist_query, case=False, na=False)]
        if artist_matches.empty:
            st.warning("No songs found for that artist in the selected date range.")
        else:
            total_count = artist_matches.shape[0]
            st.success(f"✅ {artist_query.title()} appeared **{total_count}** times as Song of the Day.")
            song_counts = artist_matches.groupby("Song Title").agg({"Date": list, "Song Title": "count"}).rename(columns={"Song Title": "Times Chosen"}).reset_index()
            st.write("🎵 **Songs by Artist**")
            for _, row in song_counts.iterrows():
                st.markdown(f"**{row['Song Title']}** — Chosen {row['Times Chosen']} time(s)")
                st.markdown(", ".join(sorted(row["Date"])))

# **Tab 3: Historically Today**
with tabs[2]:
    st.subheader("📜 Historically Today")

    # Default to today's date but allow user selection
    default_date = datetime.today().date()
    selected_date = st.date_input("Select a Date for History", value=default_date)

    # Format the selected date for filtering
    selected_month_day = selected_date.strftime("%m-%d")
    history_df = sotd_df_stream[sotd_df_stream["Date"].str.endswith(selected_month_day)]

    if history_df.empty:
        st.warning("No historical data found for this date.")
    else:
        for _, row in history_df.iterrows():
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(row["Album Art"], width=150)
            with col2:
                st.write(f"**{row['Song Title']}** by {row['Artist']} ({row['Date'][:4]})")
                st.markdown(f"<p class='historical-notes'>{row['Notes']}</p>", unsafe_allow_html=True)


# **Tab 4: Full Daily History**
with tabs[3]:
    st.subheader("📅 Full Daily History of SOTDs")

    keyword = st.text_input("🔍 Search by keyword (song, artist, or note):", key="history_search")
    history_filtered = sotd_df_stream.copy()

    if keyword:
        keyword_lower = keyword.lower()
        history_filtered = history_filtered[
            history_filtered["Song Title"].str.lower().str.contains(keyword_lower, na=False) |
            history_filtered["Artist"].str.lower().str.contains(keyword_lower, na=False) |
            history_filtered["Notes"].str.lower().str.contains(keyword_lower, na=False)
        ]
        st.success(f"🔎 {len(history_filtered)} result(s) found for **'{keyword}'**")

    history_view = history_filtered[["Date", "Song Title", "Artist", "Notes"]].sort_values(by="Date", ascending=False)
    st.dataframe(history_view, use_container_width=True, height=600)
