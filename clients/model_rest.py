import requests


class AssistantClient:
    """A client for interacting with a chat-based assistant model via a REST API."""

    def __init__(self, api_key, base_url, model, verify_ssl: bool = True):
        """
        Initializes the AssistantClient.

        Args:
            api_key (str): The API key for authentication.
            base_url (str): The base URL of the API endpoint.
            model (str): The model identifier to use for chat completions.
            verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.verify_ssl = verify_ssl

    def chat(self, messages, **kwargs):
        """
        Sends a chat request to the assistant model.

        Args:
            messages (list): A list of message dictionaries in the format expected by the API.
            **kwargs: Additional keyword arguments to pass to the API request.

        Returns:
            str: The content of the assistant's response.

        Raises:
            requests.exceptions.HTTPError: If an HTTP error occurs during the request.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            **kwargs
        }
        print("Debug - Request Payload:", payload)

        try:
            response = requests.post(f"{self.base_url}/v1/chat/completions", headers=headers, json=payload, verify=self.verify_ssl)
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]["content"]
            return message
        except requests.exceptions.HTTPError as e:
            print("HTTP Error Details:", e.response.text)
            raise

    def __call__(self, prompt, *args, **kwargs):
        """
        Enables the client instance to be called directly like a function for chat.

        Args:
            prompt (str or list): The user's message as a string, or a list of message dictionaries.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            str: The content of the assistant's response.

        Raises:
            ValueError: If the prompt is not a string or a list of messages.
        """
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            messages = prompt
        else:
            raise ValueError("prompt must be str or list of messages")       
        return self.chat(messages, **kwargs)