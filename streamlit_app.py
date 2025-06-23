import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Recruitment Dashboard", layout="wide")
st.title("Recruitment Analytics Dashboard")

st.markdown("---")

# Placeholder for job stats
def fetch_data(endpoint):
    try:
        response = requests.get(endpoint)
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return []

# Example endpoints (update as needed)
jobs = fetch_data("http://localhost:5000/jobs/")
applications = fetch_data("http://localhost:5000/submit/applications")

col1, col2 = st.columns(2)

with col1:
    st.header("Job Postings")
    if jobs:
        st.dataframe(pd.DataFrame(jobs))
    else:
        st.info("No job data available.")

with col2:
    st.header("Applications")
    if applications:
        st.dataframe(pd.DataFrame(applications))
    else:
        st.info("No application data available.")

st.markdown("---")
st.write("Expand this dashboard with more analytics and visualizations as needed.") 