#!/usr/bin/env python3
"""
Test script for the Lab Assistant without Streamlit UI
"""

import json
import os
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_tool_calling_agent, tool 
from langchain_core.prompts import ChatPromptTemplate

# --- AGGRESSIVELY DISABLE ALL LANGSMITH FEATURES ---
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_HUB_DISABLE_COLLECTION"] = "true"
if "LANGCHAIN_API_KEY" in os.environ:
    del os.environ["LANGCHAIN_API_KEY"]
os.environ["LANGCHAIN_HUB_NO_SSL_VERIFY"] = "1"

# --- LLM Configuration ---
print("🔧 Initializing Mistral model...")
llm = ChatOllama(model="mistral", temperature=0)

# Test LLM connection
try:
    test_response = llm.invoke([{"role": "user", "content": "Hello! Can you respond with just 'Connection successful'?"}])
    print(f"✅ LLM Connection Test: {test_response.content}")
except Exception as e:
    print(f"❌ LLM Connection Failed: {e}")
    exit(1)

# --- Define Tools ---
@tool
def get_patient_results_tool(patient_id: str, data_type: str = "all", location: str = "any") -> str:
    """
    Retrieves patient lab results from the LIMS (Lab Information Management System) via an MCP server.
    Args:
        patient_id (str): The unique identifier for the patient. THIS IS A MANDATORY ARGUMENT.
        data_type (str): The type of results to retrieve (e.g., "blood test", "genomic data", "all").
        location (str): The lab location to query (e.g., "lab A", "hospital B", "any").
    Returns:
        str: A simulated JSON response representing the patient's data, or an error message.
    """
    if not patient_id:
        return "Missing mandatory argument: 'patient_id'."
    
    print(f"🤖 Calling MCP Server: PatientDataService")
    print(f"📍 API Endpoint: /patient/{patient_id}/results")
    print(f"📋 Parameters: dataType={data_type}, location={location}")
    
    if patient_id == "123":
        return json.dumps({
            "status": "success",
            "patient_id": "123",
            "data_type": data_type,
            "location": location,
            "results": {
                "blood_glucose": "95 mg/dL",
                "hemoglobin": "14.2 g/dL",
                "last_test_date": "2025-06-28"
            }
        }, indent=2)
    else:
        return json.dumps({"status": "error", "message": f"Patient ID {patient_id} not found or data unavailable."}, indent=2)

@tool
def add_operator_tool(name: str, code: str) -> str:
    """
    Adds a new lab operator to the system by calling the Flask API.
    Args:
        name (str): The full name of the operator.
        code (str): A unique short code for the operator.
    Returns:
        str: Confirmation message from the API call.
    """
    if not name or not code:
        return "Missing mandatory arguments for add_operator: 'name' or 'code'."
    
    print(f"🤖 Simulating Flask API call: /add_operator_api")
    print(f"📋 Parameters: name={name}, code={code}")
    return f"✅ Successfully added operator '{name}' with code '{code}' (simulated)"

# --- Agent Setup ---
agent_tools = [get_patient_results_tool, add_operator_tool]

agent_prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a highly capable AI lab assistant. Your task is to understand user requests "
        "and use the appropriate specialized tools to fulfill the request by calling relevant 'MCP Tasks'.\n\n"
        "TOOL CALLING INSTRUCTIONS:\n"
        "1. For patient results queries: CALL get_patient_results_tool with patient_id (required), data_type (optional), location (optional)\n"
        "2. For adding operators: CALL add_operator_tool with name and code\n\n"
        "Always call the appropriate tool based on the user's request. Provide a helpful response after calling the tool."
    )),
    ("human", "{user_query}"), 
    ("placeholder", "{agent_scratchpad}")
])

print("🔧 Creating agent...")
agent_executor = AgentExecutor(
    agent=create_tool_calling_agent(llm, agent_tools, agent_prompt),
    tools=agent_tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=3,
    early_stopping_method="generate"
)

# --- Test Cases ---
test_cases = [
    "Get patient results for patient 123",
    "Add operator John Doe with code JD01"
]

print("🚀 Starting tool calling tests...\n")

for i, test_query in enumerate(test_cases, 1):
    print(f"{'='*50}")
    print(f"TEST {i}: {test_query}")
    print(f"{'='*50}")
    
    try:
        response = agent_executor.invoke({"user_query": test_query})
        print(f"✅ SUCCESS: {response['output']}")
    except Exception as e:
        print(f"❌ FAILED: {e}")
    
    print()

print("🎉 Test completed!")