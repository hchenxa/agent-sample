# Echo Chatbot

Echo Chatbot is an interactive Streamlit application designed to streamline interactions with various development and testing tools, including Large Language Models (LLMs), Jenkins CI/CD, and ReportPortal test automation dashboards. It provides a unified chat interface to query information, trigger actions, and analyze data from these platforms.

## Features

*   **Conversational AI:** Integrates with Models.corp or local Ollama instances for general chat and intelligent analysis.
*   **Jenkins Integration:**
    *   List Jenkins jobs and views.
    *   Check the status and details of specific Jenkins jobs.
    *   Trigger Jenkins jobs with optional parameters.
*   **ReportPortal Integration:**
    *   Retrieve and display test launch data.
    *   Visualize Pass Rate Trends over time.
    *   Generate a pie chart for OCP Platform Test Coverage.
    *   Identify and list the most frequent failing test cases.
    *   LLM-powered analysis of ReportPortal data.

## Setup

Follow these steps to get the Echo Chatbot running on your local machine.

### Prerequisites

*   Python 3.8+
*   `pip` (Python package installer)
*   (Optional) Docker, if you plan to use Ollama locally.

### 1. Clone the Repository

```bash
git clone https://github.com/your-repo/echo-chatbot.git
cd echo-chatbot
```

### 2. Install Dependencies

Install the required Python packages using `pip`:

```bash
pip install -r requirements.txt
```

### 3. Configuration

The application uses environment variables for sensitive information and API endpoints. Create a `.env` file in the root directory of the project and populate it with the following:

```dotenv
# --- LLM Configuration (Choose one) ---

# For Models.corp:
MODEL_API="YOUR_MODEL_CORP_API_ENDPOINT"
MODEL_ID="YOUR_MODEL_CORP_MODEL_ID"
ACCESS_TOKEN="YOUR_MODEL_CORP_ACCESS_TOKEN"

# OR for Ollama:
# OLLAMA_HOST="http://localhost:11434" # Default Ollama host
# (No model ID or access token needed for Ollama, models are fetched dynamically)

# --- Jenkins Configuration (Optional) ---
JENKINS_URL="YOUR_JENKINS_URL"
JENKINS_USERNAME="YOUR_JENKINS_USERNAME"
JENKINS_API_TOKEN="YOUR_JENKINS_API_TOKEN" # Generate an API token in Jenkins user settings

# --- ReportPortal Configuration (Optional) ---
RP_ENDPOINT="YOUR_REPORTPORTAL_ENDPOINT"
RP_UUID="YOUR_REPORTPORTAL_UUID" # Your ReportPortal API UUID
RP_PROJECT="YOUR_REPORTPORTAL_PROJECT_NAME"
# DISABLE_SSL_VERIFICATION_RP="True" # Uncomment and set to True if you have SSL issues (Insecure!)
```

**Note:** If you are using Ollama, ensure it is running and you have downloaded the desired models (e.g., `ollama run llama2`).

### 4. Run the Application

Start the Streamlit application from your terminal:

```bash
streamlit run main.py
```

This will open the Echo Chatbot in your web browser.

## Usage

Interact with the chatbot by typing commands or questions in the input box.

### General Chat

Any query not recognized as a specific command will be processed by the configured LLM.

### Jenkins Commands

(Requires Jenkins configuration in `.env`)

*   **List jobs:**
    `list jenkins jobs`
    `list jenkins jobs related to <keyword>`
*   **List views:**
    `list jenkins views`
*   **Check job status:**
    `check jenkins job <job_name>`
*   **Trigger job:**
    `trigger jenkins job <job_name>`
    `trigger jenkins job <job_name> with params param1=value1,param2=value2`

### ReportPortal Commands

(Requires ReportPortal configuration in `.env`)

*   **List launches:**
    `list launches`
    `/rp list launches component=my_component,release=1.2.3`
    `/rp list launches attribute_key:attribute_value,another_key:another_value`
    (Supports `key=value` or `key:value` for attributes, separated by commas)

*   **Generate Test Report:**
    `please help me to generate the test report of <component_name> based on the data from reportportal`
    `analysis for component <component_name> in release <release_version>`

## Troubleshooting

*   **`ModuleNotFoundError`:** Ensure all dependencies are installed (`pip install -r requirements.txt`).
*   **API Connection Errors:** Double-check your `.env` file for correct API endpoints, tokens, and usernames. Verify that the services (Ollama, Jenkins, ReportPortal) are running and accessible from your machine.
*   **SSL Certificate Errors:** If you encounter SSL errors with Jenkins or ReportPortal, you can try setting `DISABLE_SSL_VERIFICATION=True` or `DISABLE_SSL_VERIFICATION_RP=True` in your `.env` file. **Be aware that this is insecure and should only be used for development or trusted internal networks.**
*   **No LLM Response:** Ensure your LLM (Models.corp or Ollama) is correctly configured and accessible. For Ollama, verify the host and that the model is downloaded and running.

---
