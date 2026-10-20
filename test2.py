import json
import streamlit as st
import ollama

MODEL = "llama3.1"

# 1. Define the Actions (Python Functions)
def get_user_balance(user_name: str) -> str:
    """Mock database lookup action."""
    mock_db = {"alice": "\$1,250.00", "bob": "\$420.50"}
    balance = mock_db.get(user_name.lower())
    if balance is not None:
        return {
            "text": f"Database Action Result: {user_name}'s balance is \${balance:,.2f}.",
            "chart_data": None
        }
    return {"text": f"Database Action Result: User '{user_name}' not found.", "chart_data": None}

def calculate_investment_growth(principal: float, rate: float, years: int) -> dict:
    """Mathematical action that also generates numerical array history for plotting."""
    growth_history = []
    current_balance = principal

    # Generate continuous timeline steps for chart mapping
    for year in range(0, years + 1):
        growth_history.append({
            "Year": year,
            "Balance (\$)": round(current_balance, 2)
        })
        current_balance *= (1 + (rate / 100))

    future_value = growth_history[-1]["Balance (\$)"]

    return {
        "text": f"Calculation Action Result: Future value after {years} years is \${future_value:,.2f}.",
        "chart_data": growth_history  # Feed this array directly to Streamlit's visual engine
    }

available_functions = {
    "get_user_balance": get_user_balance,
    "calculate_investment_growth": calculate_investment_growth
}

# 3. Define the functions schemas for Ollama
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_user_balance",
            "description": "Retrieves the account balance for a specific user name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_name": {"type": "string", "description": "The first name of the user."}
                },
                "required": ["user_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_investment_growth",
            "description": "Calculates future value of an investment using compound interest.",
            "parameters": {
                "type": "object",
                "properties": {
                    "principal": {"type": "number", "description": "Starting money amount."},
                    "rate": {"type": "number", "description": "Annual interest rate percentage."},
                    "years": {"type": "integer", "description": "Number of years to compound."},
                },
                "required": ["principal", "rate", "years"],
            },
        },
    }
]

st.title("🦛 HypoAgent")
st.write("Give me a hypothesis. I will try to disprove – against your database.")

st.set_page_config(page_title="HypoAgent", page_icon="🦛")

user_input = st.text_input(
        "Hypothesis",
        placeholder="e.g., Cats like humans",
        label_visibility="collapsed",
        )

if st.button("Try to disprove"):
    if not user_input:
        st.warning("Please enter a hypothesis before submitting.")

    else:

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
                    st.info(f"🤖 Local LLM triggered: `{function_name}`")
                    if function_name in available_functions:
                        run_function = available_functions[function_name]
                        action_output = run_function(**function_args)
                        text_output = action_output["text"]
                        chart_payload = action_output["chart_data"]
                        st.success(text_output)
                        if chart_payload:
                            st.line_chart(chart_payload, x="Year", y="Balance (\$)")
                    else:
                        st.error(f"Triggered action '{function_name}' is not wired up in Python backend.")
            else:
                st.success(message.get("content", "No output generated."))
