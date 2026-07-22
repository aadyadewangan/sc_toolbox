import streamlit as st

st.set_page_config(page_title="Tools", page_icon="🧰", layout="centered")

st.title("🧰 SC Tool Box")
st.caption("A set of micro tools to help manage tasks and operations of scratch cards & affiliates.")

st_tools = [
    ("✂️", "Coupon Code Splitter", "Split coupon codes into smaller chunks."),
    ("📊", "Checkout Funnel Analysis", "Analyze the checkout funnel by dropping in relevant files and identify drop-off points."),
    ("📁", "Codes Repo", "Codes from those split here, for sanity checks"),
    ("🧾", "PO Generator", "Generate purchase orders for scratch card partners."),
]

ext_models = [
    ("📈", "Bottom Funnel Comparison", "Compare the performance across any 2 date ranges.", "https://docs.google.com/spreadsheets/d/1zP9kuxyyFSrytV8re36htGcUP_AxnSC4x8GNYPiHfSQ/edit?gid=0#gid=0"),
]

c1, c2 = st.columns(2)

with c1:
    for icon, name, desc in st_tools:
        with st.container(border=True):
            st.page_link(
            f"pages/{name.replace(' ', '_')}.py",
            label=f"{icon} {name}",)
            st.caption(desc)
    
        

with c2:
    for icon, name, desc, link in ext_models:
        with st.container(border=True):
            # st.text(f"{icon} {name}")
            st.link_button(f"{icon} {name}", link, type = "tertiary")
            st.caption(desc)