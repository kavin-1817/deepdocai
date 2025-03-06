import streamlit.components.v1 as components
import os

# Declare the component
_component_func = components.declare_component(
    "voice_input",
    path=os.path.dirname(os.path.abspath(__file__))
)

def voice_input(key=None):
    component_value = _component_func(key=key, default={"text": "", "error": False})
    return component_value
