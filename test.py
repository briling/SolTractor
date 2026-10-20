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

# Map string names to actual Python functions for execution
available_functions = {
    "get_user_balance": get_user_balance,
    "calculate_investment_growth": calculate_investment_growth
}

# 2. Streamlit UI Layout
st.title("🦙 Local Action-Oriented AI (Ollama)")
st.write("Your prompts are processed 100% locally on your machine.")

user_input = st.text_input("How can I help you today?", placeholder="e.g., Check Bob's balance")

if st.button("Submit Command") and user_input:

    # 3. Define the schemas of your functions for Ollama
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

    with st.spinner("Local LLM is analyzing your request..."):
        # 4. Request a response from local Ollama service
        response = ollama.chat(
            model="llama3.1", # Ensure you have pulled this model via 'ollama pull llama3.1'
            messages=[{"role": "user", "content": user_input}],
            tools=tools
        )

        message = response.get("message", {})
        tool_calls = message.get("tool_calls", [])

        # 5. Check if the local model decided to trigger an action
        if tool_calls:
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = tool_call.function.arguments  # Ollama parses arguments into a dict automatically

                st.info(f"🤖 Local LLM triggered: `{function_name}`")

                # Execute the code dynamically
                if function_name in available_functions:
                    run_function = available_functions[function_name]
                    # unpack arguments dictionary directly into the function
                    action_output = run_function(**function_args)
                    st.success(action_output)
                else:
                    st.error(f"Triggered action '{function_name}' is not wired up in Python backend.")
        else:
            # Standard conversational text response if no function matched
            st.write("🤖 AI Response:", message.get("content", "No output generated."))
