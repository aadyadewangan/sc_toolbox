import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Codes Repo", page_icon="📦", layout="centered")

st.title("📦 Codes Repo")
st.caption("Saved random code samples from each split operation.")

repo_path = "cache/codes_repo.csv"

if st.button("Refresh Repo"):
    st.experimental_rerun()

if not os.path.exists(repo_path):
    st.warning("No saved codes yet. Run the Coupon Code Splitter first.")
else:
    try:
        df = pd.read_csv(repo_path)
        if df.empty:
            st.warning("The codes repo is currently empty.")
        else:
            st.dataframe(df)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download codes repo",
                data=csv,
                file_name="codes_repo.csv",
                mime="text/csv",
            )
    except Exception as exc:
        st.error(f"Unable to read codes repo: {exc}")
