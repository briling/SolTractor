import streamlit as st
import numpy as np
import pandas as pd

st.title("🦛 HypoAgent")
st.set_page_config(page_title="HypoAgent", page_icon="🦛")

# initialize chat history in session state if it doesn't exist
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "type": "text", "content": "Chat with Nomad!"}
    ]

def display_message(message):
    with st.chat_message(message["role"]):
        if message["type"] == "text":
            st.write(message["content"])
        elif message["type"] == "line_chart":
            st.write(message["content"])
            st.line_chart(message["data"])
        elif message["type"] == "bar_chart":
            st.write(message["content"])
            st.bar_chart(message["data"])

# display existing chat history from session state
for message in st.session_state.messages:
    display_message(message)

if user_query := st.chat_input("What should I plot?"):

    st.session_state.messages.append({"role": "user", "type": "text", "content": user_query})
    display_message(st.session_state.messages[-1])

    query_lower = user_query.lower()

    if "line" in query_lower:
        text_response = "Here is your requested line chart:"
        chart_data = pd.DataFrame(np.random.randn(20, 3), columns=["A", "B", "C"])
        st.session_state.messages.append({
            "role": "assistant",
            "type": "line_chart",
            "content": text_response,
            "data": chart_data
        })

    elif "bar" in query_lower:
        text_response = "Here is your requested bar chart:"
        chart_data = pd.DataFrame(np.random.randn(10, 2), columns=["X", "Y"])
        st.session_state.messages.append({
            "role": "assistant",
            "type": "bar_chart",
            "content": text_response,
            "data": chart_data
        })

    else:
        text_response = "I didn't quite catch that. Try saying 'line chart' or 'bar chart'."
        st.session_state.messages.append({"role": "assistant", "type": "text", "content": text_response})

    display_message(st.session_state.messages[-1])
