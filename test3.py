import json
import streamlit as st
import ollama

# 1. Define the Actions (Python Functions)
def get_user_balance(user_name: str) -> str:
    """Mock database lookup action."""
    mock_db = {"alice": "\$1,250.00", "bob": "\$420.50"}
    balance = mock_db.get(user_name.lower(), "User not found")
    return f"Database Action Result: {user_name}'s balance is {balance}."

def calculate_investment_growth(principal: float, rate: float, years: int) -> str:
    """Mathematical action."""
    future_value = principal * ((1 + (rate / 100)) ** years)
    return f"Calculation Action Result: Future value is \${future_value:,.2f}"

available_functions = {
    "get_user_balance": get_user_balance,
    "calculate_investment_growth": calculate_investment_growth
}

# 2. Set up Tool Schemas for Ollama
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

# 3. Streamlit Page Configuration
st.title("🦙 Continuous Local Action Loop")
st.write("Your session state is saved. Keep asking questions to trigger more actions!")

# Initialize session state memory loop if it doesn't exist yet
if "messages" not in st.session_state:
    st.session_state.messages = []

# 4. Display past loop items in UI
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if "action" in msg:
            st.info(f"🔧 **Triggered Action:** `{msg['action']}`")
        st.write(msg["content"])

# 5. Capture continuous user text input via chat box loop
if user_input := st.chat_input("Ask a question (e.g., 'Check Alice's balance' or 'Hi!')"):

    # Render user prompt immediately to UI
    with st.chat_message("user"):
        st.write(user_input)

    # Store user command in history log
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        with st.spinner("Local LLM processing..."):

            # Request response matching from Ollama
            response = ollama.chat(
                model="llama3.1",
                messages=[{"role": "user", "content": user_input}],
                tools=tools
            )

            message = response.get("message", {})
            tool_calls = message.get("tool_calls", [])

            # Check for action loops
            if tool_calls:
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = tool_call.function.arguments

                    st.info(f"🔧 **Triggered Action:** `{function_name}`")

                    if function_name in available_functions:
                        run_function = available_functions[function_name]
                        action_output = run_function(**function_args)
                        st.success(action_output)

                        # Store action data into session loop memory
                        st.session_state.messages.append({
                            "role": "assistant",
                            "action": function_name,
                            "content": action_output
                        })
                    else:
                        st.error("Action not mapped.")
            else:
                # Text reply fallback
                content = message.get("content", "No response.")
                st.write(content)
                st.session_state.messages.append({"role": "assistant", "content": content})
