import streamlit.components.v1 as components

# Load the local JavaScript file
components.html(
    """
    <script src="./frontend/voice_input.js"></script>
    <div id="voice-input"></div>
    <script>
        // Initialize the voice input component
        VoiceInput.init("#voice-input");
    </script>
    """
)
