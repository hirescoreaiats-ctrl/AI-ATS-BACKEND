import streamlit as st
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="HireIQ ATS", layout="wide")
st.title("HireIQ - AI Hiring Platform")
st.markdown("---")

# 🔹 Step 1: Create Job
st.subheader("Step 1: Create Job")

jd_text = st.text_area("Paste Job Description", height=200)

if st.button("Create Job"):
    if jd_text.strip():
        response = requests.post(
            f"{API_URL}/create-job",
            json={"jd_text": jd_text}
        )

        if response.status_code == 200:
            data = response.json()
            st.session_state["job_id"] = data["job_id"]
            st.success(f"Job Created ✅ | Job ID: {data['job_id']}")
        else:
            st.error("Error creating job")
    else:
        st.warning("Please paste JD first")

# 🔹 Step 2: Upload Resumes
if "job_id" in st.session_state:

    st.subheader("Step 2: Upload Resumes")

    uploaded_files = st.file_uploader(
        "Upload Resumes (PDF / DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True
    )

    if st.button("Process Resumes"):
        if not uploaded_files:
            st.warning("Upload at least one resume")
        else:
            files = [
                ("files", (file.name, file.getvalue()))
                for file in uploaded_files
            ]

            with st.spinner("Processing resumes..."):
                response = requests.post(
                    f"{API_URL}/upload-resumes/{st.session_state['job_id']}",
                    files=files
                )

            if response.status_code == 200:
                st.success("Resumes processed successfully ✅")
            else:
                st.error("Error processing resumes")

# 🔹 Step 3: View Results
if "job_id" in st.session_state:

    st.subheader("Step 3: View Results")

    if st.button("Get Results"):
        response = requests.get(
            f"{API_URL}/results/{st.session_state['job_id']}"
        )

        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame(data["results"])

            if not df.empty:
                df = df.sort_values("final_score", ascending=False)

            st.dataframe(df, use_container_width=True)

            st.download_button(
                "Download CSV",
                df.to_csv(index=False),
                "results.csv",
                "text/csv"
            )
        else:
            st.error("Error fetching results")