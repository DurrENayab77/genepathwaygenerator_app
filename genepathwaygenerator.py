import streamlit as st
import requests
from typing import List, Tuple
import pandas as pd
from pyvis.network import Network
import streamlit.components.v1 as components
import tempfile
import os
import google.generativeai as genai
import streamlit as st
import google.generativeai as genai

gemini_key = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=gemini_key)

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Gene Pathway Generator",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Gene Pathway Generator")
st.caption("Powered by STRING database • Interactive network visualization")

# ---------------- SIDEBAR ----------------
score_threshold = st.slider(
    "Minimum confidence score",
    min_value=0.0,
    max_value=1.0,
    value=0.7,
    step=0.05
)

show_edge_weight = st.checkbox("Show edge confidence scores", value=True)

# Gemini API key (hide in production)


st.info("Species: Homo sapiens (NCBI taxon 9606)")

# ---------------- STRING API ----------------
@st.cache_data(show_spinner=False, ttl=3600)
def get_gene_interactions(genes: List[str], score_threshold: float = 0.7) -> List[Tuple[str, str, float]]:
    if len(genes) < 2:
        return []

    url = "https://string-db.org/api/json/network"
    params = {
        "identifiers": "\r".join(genes),
        "species": 9606,
        "caller_identity": "streamlit-app"
    }

    try:
        with st.spinner(f"Querying STRING DB for {len(genes)} genes..."):
            response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            st.error(f"STRING API error: HTTP {response.status_code}")
            return []

        data = response.json()
        edges = []
        for interaction in data:
            score = interaction.get("score", 0.0)
            if score < score_threshold:
                continue
            a = interaction["preferredName_A"]
            b = interaction["preferredName_B"]
            if a in genes and b in genes:
                edges.append((a, b, score))
        return edges

    except requests.exceptions.RequestException as e:
        st.error(f"Network error: {e}")
        return []

# ---------------- PYVIS NETWORK ----------------
def create_interactive_network(genes: List[str], edges: List[Tuple[str, str, float]]) -> str:
    net = Network(
        height="700px",
        width="100%",
        bgcolor="#f8f9fa",
        font_color="black",
        directed=False,
        cdn_resources="remote"
    )

    pastel_colors = [
        "#FFB3BA", "#FFDFBA", "#FFFFBA",
        "#BAFFC9", "#BAE1FF", "#E2BAFF", "#FFC3E1"
    ]

    for i, gene in enumerate(genes):
        net.add_node(
            gene,
            label=gene,
            color=pastel_colors[i % len(pastel_colors)],
            size=24
        )

    for a, b, score in edges:
        title_text = f"Confidence: {score:.2f}" if show_edge_weight else ""
        net.add_edge(
            a,
            b,
            title=title_text,
            width=1 + score * 2,
            color="#9e9e9e"
        )

    net.set_options("""
    {
      "interaction": {
        "hover": true,
        "dragNodes": true,
        "hoverConnectedEdges": true,
        "navigationButtons": true
      },
      "physics": {
        "enabled": true,
        "stabilization": {
          "enabled": true,
          "iterations": 120
        },
        "barnesHut": {
          "gravitationalConstant": -2500,
          "centralGravity": 0.15,
          "springLength": 130,
          "springConstant": 0.02,
          "damping": 0.6,
          "avoidOverlap": 0.7
        }
      },
      "nodes": {
        "shape": "dot",
        "font": {
          "size": 14
        }
      },
      "edges": {
        "smooth": {
          "type": "dynamic"
        }
      }
    }
    """)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    net.save_graph(tmp.name)
    return tmp.name

# ---------------- GEMINI AI SUMMARY ----------------
def generate_ai_summary(interactions: List[Tuple[str, str, float]]) -> str:
    if not interactions:
        return "No interactions to summarize."

    interaction_lines = [f"{a} interacts with {b} (confidence {score:.2f})" for a, b, score in interactions]
    prompt_text = "\n".join(interaction_lines)

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")

        full_prompt = f"""You are an expert in molecular biology and bioinformatics pathway analysis.

You are given a list of gene–gene interactions with confidence scores obtained from a trusted protein–protein interaction database.

Your task is to interpret these interactions using established biological knowledge only.

Guidelines:
• Describe an interaction as “activates” or “inhibits” only if this relationship is well supported in known signaling pathways.
• If the direction or functional effect is uncertain, describe the interaction as “associative”, “regulatory”, or “functionally related”.
• Do not assume causality where it is not clearly established.
• If recognizable, mention the major signaling pathway(s) or biological process(es) involved (e.g., MAPK signaling, cell cycle regulation, apoptosis).
• Summarize the overall biological implication of the interactions in 3–4 clear, connected sentences.

Strict rules:
• Do NOT invent genes, interactions, directions, or biological effects.
• Base conclusions only on widely accepted biological knowledge.
• Use simple, clear, human-readable biological language.
• Avoid technical jargon, headings, bullet points, or formatting.
• Write as a concise explanatory paragraph suitable for a scientific web application.

Here are the gene interactions:

{prompt_text}
"""
        response = model.generate_content(full_prompt)
        summary = response.text

        # Optional: highlight activates/inhibits
        summary = summary.replace(
            "activates", "<span style='color:green;font-weight:bold'>activates</span>"
        )
        summary = summary.replace(
            "inhibits", "<span style='color:red;font-weight:bold'>inhibits</span>"
        )
        return summary

    except Exception as e:
        return f"Could not generate summary: {e}"

# ---------------- STREAMLIT UI ----------------
st.markdown("### Enter gene symbols")
genes_input = st.text_area(
    "Paste gene symbols (comma / space / newline separated)",
    height=150,
    placeholder="EGFR\nKRAS\nBRAF\nMAPK1\nTP53"
)

if st.button("Generate Pathway ", type="primary"):
    if not genes_input.strip():
        st.error("Please enter gene symbols.")
    else:
        genes = sorted(set(g.upper().strip() for g in genes_input.replace(",", " ").split() if g.strip()))
        if len(genes) < 2:
            st.warning("Enter at least two genes.")
        else:
            st.success(f"Processing {len(genes)} genes")
            interactions = get_gene_interactions(genes, score_threshold)
            st.write(f"🔗 Found {len(interactions)} interactions")

            if not interactions:
                st.info("No interactions found. Try lowering the threshold.")
            else:
                html_file = create_interactive_network(genes, interactions)
                st.subheader("Gene Interaction Network")
                components.html(open(html_file).read(), height=700)
                os.remove(html_file)

                with st.expander("View interaction table"):
                    df = pd.DataFrame(interactions, columns=["Gene A", "Gene B", "Confidence"])
                    df = df.sort_values("Confidence", ascending=False)
                    st.dataframe(df, use_container_width=True)

                # AI Summary box with white background
                st.subheader("Interaction Summary")
                summary_text = generate_ai_summary(interactions)
                st.markdown(
                    f"""
                    <div style="
                        background-color:#ffffff;
                        border-left:5px solid #4a90e2;
                        padding:15px;
                        border-radius:10px;
                        font-size:16px;
                        color:#0a2e5d;
                        line-height:1.5;
                        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
                    ">
                        {summary_text}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Download CSV
                csv_file = pd.DataFrame(interactions, columns=["Gene A", "Gene B", "Confidence"]).to_csv(index=False)
                st.download_button(
                    "Download Interactions CSV",
                    data=csv_file,
                    file_name="gene_interactions.csv",
                    mime="text/csv"
                )
