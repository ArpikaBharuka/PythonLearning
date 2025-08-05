import streamlit as st
import json
import os 
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_tool_calling_agent, tool 
from langchain_core.prompts import ChatPromptTemplate
import requests 

# --- Streamlit UI Page Configuration (MUST BE FIRST Streamlit COMMAND) ---
st.set_page_config(page_title="Lab Assistant: LLM Agent with MCP Concept", layout="wide")

# --- Streamlit UI Main Heading ---
st.title("🔬 Lab Assistant: LLM Agent with MCP Concept")
st.markdown("Enter your request. The assistant will identify its intent and call the appropriate 'MCP Task'.")

# --- AGGRESSIVELY DISABLE ALL LANGSMITH FEATURES ---
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_HUB_DISABLE_COLLECTION"] = "true"
if "LANGCHAIN_API_KEY" in os.environ:
    del os.environ["LANGCHAIN_API_KEY"]
os.environ["LANGCHAIN_HUB_NO_SSL_VERIFY"] = "1"

FLASK_APP_BASE_URL = "http://127.0.0.1:5000"

# --- LLM Configuration ---
llm = ChatOllama(model="mistral", temperature=0) 

# --- Define the complete System Prompt for Initial NLP Pass ---
SYSTEM_PROMPT_CONTENT = """
You are an intelligent NLP assistant for a lab. Your task is to analyze user queries 
to accurately identify their primary intent and extract relevant entities. 
Always output your response as a JSON object with the following structure:
```json
{
  "original_query": "<user's exact query>",
  "detected_intent": "<one of: Patient Results Inquiry, Operator Management, Training Management, Unrecognized Intent>",
  "meaningful_keywords": ["keyword1", "keyword2"],
  "extracted_entities": {
    "entity_type1": "value1",
    "entity_type2": "value2"
  },
  "raw_query_for_agent": "<user's exact query>"
}
```

Intent Definitions and Expected Entities:

Patient Results Inquiry: User wants lab results or patient records. (Entities: patient_id (e.g., '123', 'XYZ'), data_type (e.g., 'patient results', 'blood test'), location (e.g., 'lab', 'hospital')).

Operator Management: User wants to add or remove lab operators.

If action is 'add': (Entities: action ('add'), operator_name (e.g., 'John Doe'), operator_code (e.g., 'JD01')).

If action is 'remove': (Entities: action ('remove'), operator_id (e.g., '4')).

Training Management: User wants to assign or delete operator trainings. (Entities: action (e.g., 'assign', 'delete'), operator_id (e.g., '3'), training_name (e.g., 'General Safety Training'), expire_date (e.g., '2025-12-31'), training_id (e.g., '5')).

Unrecognized Intent: If the query does not fit any of the above categories.

Extract all relevant entities. If an entity is not found, omit its key from the extracted_entities object. If no entities are found for an intent, provide an empty object {}. Ensure meaningful_keywords is a list of important words from the query (lowercase).
"""

def analyze_user_query_with_llm(user_query: str):
    messages_for_llm = [
        {"role": "system", "content": SYSTEM_PROMPT_CONTENT},
        {"role": "user", "content": user_query}
    ]
    try:
        response_content = llm.invoke(messages_for_llm).content 
        
        # --- MORE ROBUST JSON CLEANING ---
        json_string = response_content.strip() # Remove leading/trailing whitespace
        
        # Remove markdown code block fences if they exist
        if json_string.startswith("```json"):
            json_string = json_string[len("```json"):].strip()
        if json_string.endswith("```"):
            json_string = json_string[:-len("```")].strip()
        
        # --- Attempt to find the first '{' and last '}' to isolate JSON ---
        # This handles cases where there's preamble or postamble text
        first_brace = json_string.find('{')
        last_brace = json_string.rfind('}')
        
        if first_brace == -1 or last_brace == -1:
            raise json.JSONDecodeError("JSON object not found in response", json_string, 0)
        
        json_string = json_string[first_brace : last_brace + 1]
        # --- END ROBUST JSON CLEANING ---

        parsed_data = json.loads(json_string)
        
        if not all(k in parsed_data for k in ["detected_intent", "extracted_entities", "meaningful_keywords"]):
            raise ValueError("LLM output is missing essential keys.")
        
        return parsed_data
        
    except json.JSONDecodeError as e:
        st.error(f"Error decoding JSON from LLM response: {e}. Raw response:\n`{response_content}`")
        return {
            "original_query": user_query, "detected_intent": "Parsing Error / Unrecognized Intent",
            "meaningful_keywords": [], "extracted_entities": {}, "raw_query_for_agent": user_query
        }
    except Exception as e:
        st.error(f"An unexpected error occurred during LLM analysis: {e}")
        return {
            "original_query": user_query, "detected_intent": "Error during Analysis",
            "meaningful_keywords": [], "extracted_entities": {}, "raw_query_for_agent": user_query
        }

# Helper function to make POST requests to Flask app
def _call_flask_api(endpoint: str, data: dict) -> str:
    full_url = f"{FLASK_APP_BASE_URL}{endpoint}"
    try:
        headers = {"X-API-TOKEN": "my_super_secret_lab_api_key"} 
        response = requests.post(full_url, data=data, headers=headers)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        if response.status_code == 200:
            return f"Operation to {endpoint} successful (Status: {response.status_code}). Please check Flask app for details."
        else:
            return f"Operation to {endpoint} failed (Status: {response.status_code}). Response: {response.text}"
    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to Flask app at {FLASK_APP_BASE_URL}. Is it running?"
    except requests.exceptions.RequestException as e:
        return f"API call to {endpoint} failed: {e}"

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
    
    return _call_flask_api("/add_operator_api", {"name": name, "code": code})

@tool
def delete_operator_tool(operator_id: str) -> str:
    """
    Deletes a lab operator and all their associated trainings from the system via Flask API.
    Args:
        operator_id (str): The ID of the operator to delete.
    Returns:
        str: Confirmation message from the API call.
    """
    if not operator_id:
        return "Missing mandatory argument for delete_operator: 'operator_id'."
    return _call_flask_api(f"/delete_operator/{operator_id}", {}) # Flask expects POST, ID in URL

@tool
def assign_training_tool(operator_id: str, training_name: str, expire_date: str = "N/A") -> str:
    """
    Assigns a training to an operator via the Flask API.
    Args:
        operator_id (str): The ID of the operator.
        training_name (str): The name of the training.
        expire_date (str): The expiration date of the training (YYYY-MM-DD), default 'N/A'.
    Returns:
        str: Confirmation message from the API call.
    """
    if not operator_id or not training_name:
        return "Missing mandatory arguments for assign_training: 'operator_id' or 'training_name'."
    return _call_flask_api("/add_training", {"operator_id": operator_id, "training": training_name, "expire_date": expire_date})

@tool
def delete_training_tool(training_id: str) -> str:
    """
    Deletes a specific training record from the system via Flask API.
    Args:
        training_id (str): The ID of the training record to delete.
    Returns:
        str: Confirmation message from the API call.
    """
    if not training_id:
        return "Missing mandatory argument for delete_training: 'training_id'."
    return _call_flask_api(f"/delete_training/{training_id}", {}) # Flask expects POST, ID in URL

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
    
    st.write(f"**🤖 Calling MCP Server: PatientDataService**")
    st.write(f"**API Endpoint:** `/patient/{patient_id}/results`")
    st.write(f"**Parameters:** `dataType={data_type}`, `location={location}`")
    
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
    elif patient_id == "error_id": 
        return json.dumps({"status": "error", "message": f"Patient ID {patient_id} caused a simulated database error."}, indent=2)
    else:
        return json.dumps({"status": "error", "message": f"Patient ID {patient_id} not found or data unavailable."}, indent=2)

# --- Agent Setup ---
agent_tools = [
    get_patient_results_tool,
    add_operator_tool,      
    delete_operator_tool, 
    assign_training_tool,  
    delete_training_tool  
]

agent_prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a highly capable AI lab assistant. Your task is to understand user requests, "
        "leveraging initial NLP analysis, and then use the appropriate specialized tools "
        "to fulfill the request by calling relevant 'MCP Tasks'.\n\n"
        "Initial NLP Analysis Result:\n"
        "Original Query: {original_query}\n"
        "Detected Intent: {detected_intent}\n"
        "Meaningful Keywords: {meaningful_keywords}\n"
        "Extracted Entities: {extracted_entities_json}\n\n"
        "Based on this analysis, YOU MUST CHOOSE AND CALL ONE OF YOUR AVAILABLE TOOLS to fulfill the user's request. "
        "Provide a helpful response to the user after calling the tool. "
        "If the detected intent is 'Unrecognized Intent' or 'Error during Analysis', state that you cannot fulfill the request.\n\n"
        
        "TOOL CALLING INSTRUCTIONS:\n"
        "1. For 'Patient Results Inquiry': CALL get_patient_results_tool with patient_id (required), data_type (optional), location (optional)\n"
        "2. For 'Operator Management':\n"
        "   - If action is 'add': CALL add_operator_tool with name=operator_name, code=operator_code\n"
        "   - If action is 'remove': CALL delete_operator_tool with operator_id=operator_id\n"
        "3. For 'Training Management':\n"
        "   - If action is 'assign': CALL assign_training_tool with operator_id, training_name, expire_date (optional)\n"
        "   - If action is 'delete': CALL delete_training_tool with training_id\n\n"
        
        "Extract the required parameters from the extracted_entities JSON. If required parameters are missing, "
        "inform the user what information is needed.\n\n"
        "Your final response should be concise and directly reflect the tool's output or your decision."
    )),
    ("human", "{user_raw_query}"), 
    ("placeholder", "{agent_scratchpad}")
])

agent_executor = AgentExecutor(
    agent=create_tool_calling_agent(llm, agent_tools, agent_prompt),
    tools=agent_tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=3,  # Limit iterations to prevent infinite loops
    early_stopping_method="generate"  # Stop early if tool calling fails
)

# --- Streamlit UI ---
user_query = st.text_area(
    "What can I help you with today in the lab?",
    height=150,
    placeholder="e.g., 'Get the patient results of the lab for patient id - 123'"
)

if st.button("Analyze & Fulfill Request", type="primary"):
    if user_query:
        st.subheader("Step 1: Understanding Request (LLM-Driven NLP Pass)...")
        
        nlp_output_data = analyze_user_query_with_llm(user_query)
        
        st.write("---")
        st.write("**Initial NLP Analysis Result (JSON for Agent):**")
        st.json(nlp_output_data)

        detected_intent = nlp_output_data.get("detected_intent", "Unrecognized Intent")
        extracted_entities = nlp_output_data.get("extracted_entities", {})
        meaningful_keywords = nlp_output_data.get("meaningful_keywords", [])

        st.subheader(f"Step 2: Fulfilling Request (Agent Execution for '{detected_intent}')...")
        
        if detected_intent in ["Unrecognized Intent", "Parsing Error / Unrecognized Intent", "Error during Analysis"]:
            st.error("I'm sorry, I couldn't understand your request or there was an error in the initial analysis. Please try rephrasing.")
        else:
            try:
                agent_execution_input = {
                    "original_query": user_query,
                    "detected_intent": detected_intent,
                    "meaningful_keywords": ", ".join(meaningful_keywords),
                    "extracted_entities_json": json.dumps(extracted_entities), 
                    "user_raw_query": user_query 
                }

                with st.spinner("Agent is planning and executing task... This involves calling simulated MCP APIs."):
                    agent_response = agent_executor.invoke(agent_execution_input)
                
                st.write("---")
                st.subheader("Agent's Final Response:")
                st.markdown(agent_response["output"])

            except Exception as e:
                st.error(f"An error occurred during agent execution: {e}")
                st.info("Please check the terminal for detailed agent execution logs (if verbose is true). Common issues include LLM connection, model not supporting tool-calling, or agent misinterpreting prompt.")
    else:
        st.warning("Please enter your request in the text area.")

st.markdown("""
---
**How it works:**
This **Hybrid AI Lab Assistant** first uses an LLM to precisely understand your request (intent & entities). Then, a **single LangChain Agent** uses that structured understanding to decide which **'MCP Task' (simulated API tool call)** to execute to fulfill your request.
""")