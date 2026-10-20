import time
import json
import pandas as pd
import streamlit as st
import ollama

MODEL = "llama3.1"

# 1. Define the Actions (Python Functions)

def get_dataset(dataset: str) -> dict:
    """Retrieves the dataset needed to answer the question."""
    time.sleep(5)
    dataset = dataset.lower()
    if dataset not in ["odor", "perovskite"]:
        return {"text": f"Dataset Action Result: Dataset '{dataset}' not found.", "chart_data": None, "data": None}
    if dataset=="odor":
        df1 = pd.read_csv('data/odor/molecules.csv')
        df2 = pd.read_csv('data/odor/behavior.csv')
        df = pd.concat((df1, df2), axis=1).drop('Stimulus', axis=1)
    elif dataset=="perovskite":
        df = None
    return {
        "text": f"Dataset Action Result: Retrieved '{dataset}' dataset successfully.",
        "chart_data": None,
        "data": df,
    }


available_functions = {
    "get_dataset": get_dataset,
}


# 3. Define the functions schemas for Ollama
tools = [

    { "type": "function",
        "function": {
            "name": "get_dataset",
            "description": "Retrieves the dataset needed to answer the question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {
                        "type": "string",
                        "enum": ["odor", "perovskite"],
                        "description": "The dataset key."
                        }
                },
                "required": ["dataset"],
            },
        },
    },
]

st.title("🦛 HypoAgent")
st.write("Give me a hypothesis. I will try to disprove – against your database.")

st.set_page_config(page_title="HypoAgent", page_icon="🦛")

user_input = st.text_input(
        "Hypothesis",
        placeholder="e.g., Heavy molecules smell like fruit.",
        label_visibility="collapsed",
        )

if st.button("Try to disprove"):
    if not user_input:
        st.warning("Please enter a hypothesis before submitting.")

    else:

        dataset = None
        with st.spinner("Analyzing your request..."):
            response = ollama.chat(
                model=MODEL,
                messages=[{"role": "user", "content": user_input}],
                tools=tools
            )
            message = response.get("message", {})
            tool_calls = message.get("tool_calls", [])
        if tool_calls:
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = tool_call.function.arguments
                st.info(f"Action triggered: `{function_name}`")
                if function_name not in available_functions:
                    st.error(f"Triggered action '{function_name}' is not wired up in Python backend.")
                elif function_name != "get_dataset":
                    st.error(f"Triggered action '{function_name}' should not be triggered.")
                else:
                    with st.spinner(f"Executing action `{function_name}`..."):
                        run_function = available_functions[function_name]
                        action_output = run_function(**function_args)
                        text_output = action_output["text"]
                        #chart_payload = action_output["chart_data"]
                        st.success(text_output)
                        #if chart_payload:
                        #    st.line_chart(chart_payload, x="Year", y="Balance (\$)")
                        if "data" in action_output and action_output["data"] is not None:
                            dataset = action_output["data"]
        else:
            st.success(message.get("content", "No output generated."))

        if dataset is None:
            st.error(f"No data loaded.")

        st.dataframe(dataset)
        with st.spinner("Analyzing the dataset..."):
            prompt = f"""
            Which columns in the dataset are relevant to the hypothesis: '{user_input}'?
            Provide only a json output with the relevant columns for the signal and the target.
            The columns should not overlap.
            Columns should be in the format: {{"signal": ["column1", "column2"], "target": ["column3", "column4"]}}.
            Columns in the dataset are: {list(dataset.columns)}.
            """
            response = ollama.chat(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            message = response.get("message", {})
            content = message.get("content")

            if not content:
                st.error("No relevant columns found in the dataset.")
            st.info(content)
            content = content[content.find('{'):len(content)-content[::-1].find('}')]
            if not content:
                st.error("No relevant columns found in the dataset.")
            columns = json.loads(content)
            if "signal" not in columns or "target" not in columns:
                st.error("Relevant columns not found in the dataset.")
            if not columns["signal"] or not columns["target"]:
                st.error("Relevant columns not found in the dataset.")

            st.success(f"Relevant columns found in the dataset: signal: {columns['signal']}, target: {columns['target']}")

            dataset["signal"] = dataset[columns["signal"]].apply(lambda row: any(row), axis=1) if len(columns["signal"]) > 1 else dataset[columns["signal"]].copy()
            dataset["target"] = dataset[columns["target"]].apply(lambda row: any(row), axis=1) if len(columns["target"]) > 1 else dataset[columns["target"]].copy()
            correlation = dataset[["signal", "target"]].corr()
            st.write("Correlation between signal and target columns:")
            st.dataframe(correlation)


        with st.spinner("Concluding..."):
            c = correlation['signal']['target']
            prompt = f"""
            The correlation between the signal and target columns is {c}. Is this correlation enough to disprove the hypothesis: '{user_input}'?
            Add a smiling or sad emoji in the beginning of your answer to indicate if the hypothesis is disproved or not.
            """
            response = ollama.chat(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            message = response.get("message", {})
            content = message.get("content", "No output generated.")
            st.success(content)





