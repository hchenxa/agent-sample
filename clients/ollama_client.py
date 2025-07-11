import ollama

class OllamaClient:
    def __init__(self, host="http://localhost:11434"):
        # The ollama library automatically uses OLLAMA_HOST environment variable
        # or defaults to http://localhost:11434.
        # We can set it here if we want to override, but for simplicity,
        # we'll rely on the default or environment variable for now.
        # If a custom host is truly needed, the ollama library might need
        # to be configured differently or a custom client session used.
        self.host = host
        print(f"OllamaClient initialized with host: {self.host}")

    def generate_text(self, model: str, prompt: str):
        """
        Generates text using the specified Ollama model.

        Args:
            model (str): The name of the Ollama model to use (e.g., 'llama2', 'mistral').
            prompt (str): The input prompt for text generation.

        Returns:
            str: The generated text response.
        """
        try:
            response = ollama.generate(model=model, prompt=prompt)
            return response['response']
        except Exception as e:
            print(f"Error generating text with Ollama: {e}")
            return f"Error: {e}"

    def chat(self, model: str, messages: list):
        """
        Conducts a chat conversation with the specified Ollama model.

        Args:
            model (str): The name of the Ollama model to use.
            messages (list): A list of message dictionaries, e.g.,
                             [{'role': 'user', 'content': 'Hello!'}]

        Returns:
            str: The content of the model's response.
        """
        try:
            response = ollama.chat(model=model, messages=messages)
            return response['message']['content']
        except Exception as e:
            print(f"Error in Ollama chat: {e}")
            return f"Error: {e}"

if __name__ == '__main__':
    # Example usage:
    # Make sure Ollama is running and you have a model pulled (e.g., ollama pull llama2)
    client = OllamaClient()
    print("--- Testing generate_text ---")
    generated_response = client.generate_text(model='llama2', prompt='Tell me a short joke.')
    print(f"Generated: {generated_response}")

    print("")
    print("--- Testing chat ---")
    chat_messages = [
        {'role': 'user', 'content': 'What is the capital of France?'},
    ]
    chat_response = client.chat(model='llama2', messages=chat_messages)
    print(f"Chat response: {chat_response}")
