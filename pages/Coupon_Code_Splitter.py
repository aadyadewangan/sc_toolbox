import io
import os
import random
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Coupon Code Splitter", page_icon="✂️", layout="centered")

REPO_DIR = Path("cache")
REPO_FILE = REPO_DIR / "codes_repo.csv"


def reset():
    st.session_state["split_done"] = False
    st.session_state.pop("chunks", None)


def append_codes_repo(code, source_name, chunk_size, total_codes):
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_file": source_name,
        "chunk_size": chunk_size,
        "total_codes": total_codes,
        "random_code": code,
    }
    df = pd.DataFrame([row])
    df.to_csv(REPO_FILE, mode="a", header=not REPO_FILE.exists(), index=False)


prefix = st.text_input("Prefix for Zip File", key="prefix", on_change=reset)
uploaded_file = st.file_uploader("Upload Zip of Coupon Codes", type=["zip"], key="zip_file", on_change=reset)
chunk_size = st.number_input("Chunk Size", min_value=1, value=500000, step=50000, key="chunk_size", on_change=reset)

if st.button("Split Codes", key="split_button") and uploaded_file is not None:
    try:
        dfs = []
        with zipfile.ZipFile(uploaded_file) as z:
            for file in z.namelist():
                if file.endswith(".csv"):
                    with z.open(file) as f:
                        dfs.append(pd.read_csv(f))

        if not dfs:
            st.error("No CSV files found inside the zip.")
            st.stop()

        combined_df = pd.concat(dfs, ignore_index=True)

        # Force the header to "Vouchers" (assumes a single column of codes)
        combined_df.columns = ["Vouchers"]

        LAKH = 100_000
        total_len = len(combined_df)

        random_code = combined_df["Vouchers"].sample(n=1, random_state=random.randint(0, 2**32 - 1)).iloc[0]
        append_codes_repo(random_code, uploaded_file.name, chunk_size, total_len)

        chunks = []  # list of (filename, bytes)
        for i in range(0, total_len, chunk_size):
            start_row = i + 1
            end_row = min(i + chunk_size, total_len)

            # Round to nearest lakh, but clamp the end to the true total
            start_lakh = (start_row + LAKH - 1) // LAKH   # ceil
            end_lakh = (end_row + LAKH - 1) // LAKH        # ceil, capped by total_len

            fname = f"{prefix}_{start_lakh}_{end_lakh}L.csv"

            df_chunk = combined_df.iloc[i:i + chunk_size]
            csv_bytes = df_chunk.to_csv(index=False).encode("utf-8")
            chunks.append((fname, csv_bytes))

        st.session_state["chunks"] = chunks
        st.session_state["split_done"] = True

    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        st.info("Please check the uploaded file format and try again.")

# Show downloads after a successful split (persists across reruns)
if st.session_state.get("split_done"):
    chunks = st.session_state["chunks"]
    st.success(f"Done splitting into {len(chunks)} file(s)!")

    st.subheader("Download individual files")
    for fname, data in chunks:
        st.download_button(
            label=f"⬇️ {fname}",
            data=data,
            file_name=fname,
            mime="text/csv",
            key=f"dl_{fname}",
        )

    # Optional: still offer everything as one zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for fname, data in chunks:
            zipf.writestr(fname, data)
    zip_buffer.seek(0)

    st.divider()
    st.download_button(
        "⬇️ Download all as ZIP",
        data=zip_buffer,
        file_name=f"{prefix}.zip",
        mime="application/zip",
        key="dl_zip",
    )