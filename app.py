"""Streamlit app for the UI to query the RAG with chat interface"""

import logging
import sys
import time
from dataclasses import dataclass
from queue import Empty, Queue

import streamlit as st
import torch
from flyde.flow import Flow
from flyde.io import EOF

# =============================================================================
# CONFIGURATION & SETUP
# =============================================================================

# Configure logging to show in console (avoid duplicates)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
else:
    # If already configured, just set the level
    logging.getLogger().setLevel(logging.INFO)

# Fix streamlit torch classes path warning
torch.classes.__path__ = []  # type: ignore

# Page config
st.set_page_config(page_title="SWLWI Knowledge Base", page_icon="🚀", layout="wide")

# =============================================================================
# CORE APPLICATION LOGIC
# =============================================================================


@dataclass
class FlowWrapper:
    flow: Flow
    query: Queue
    response: Queue


@st.cache_resource
def wrap_flow() -> FlowWrapper:
    """Load and initialize the RAG flow with error handling."""
    try:
        with st.spinner("🚀 Loading knowledge base..."):
            flow = Flow.from_file("Rag.flyde")
            query_q = flow.node.inputs["query"].queue
            response_q: Queue = Queue()
            flow.node.outputs["response"].connect(response_q)
            flow.run()
            return FlowWrapper(flow, query_q, response_q)
    except Exception as e:
        st.error(f"❌ Failed to load knowledge base: {str(e)}")
        st.stop()


def get_response_with_timeout(response_queue: Queue, timeout: int = 120) -> str:
    """Get response from queue with timeout handling."""
    logging.info(f"Waiting for response with {timeout}s timeout...")
    try:
        response = response_queue.get(timeout=timeout)
        logging.info("Response received successfully")
        return response
    except Empty:
        logging.warning(f"Request timed out after {timeout} seconds")
        return "⚠️ Request timed out. Please try again with a shorter question or check if the model is running."


def show_typing_indicator(placeholder):
    """Show animated typing indicator."""
    for i in range(3):
        placeholder.markdown("🤔 Assistant is thinking" + "." * (i + 1))
        time.sleep(0.3)


def handle_exit_command():
    """Handle graceful exit when user types /bye."""
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown("👋 **Goodbye! Thanks for using SWLWI Knowledge Base!**")
    try:
        st.session_state.flow_wrapper.query.put(EOF)
    except Exception:
        pass
    st.balloons()
    time.sleep(2)
    st.stop()


def process_user_query(prompt: str, flow_wrapper: FlowWrapper) -> str:
    """Process user query and return response."""
    logging.info(f"Sending query: {prompt[:50]}...")
    flow_wrapper.query.put(prompt)
    response = get_response_with_timeout(flow_wrapper.response)

    if response == EOF:
        st.markdown("👋 **Goodbye! Thanks for using SWLWI Knowledge Base!**")
        st.balloons()
        st.stop()

    return response


def initialize_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "flow_wrapper" not in st.session_state:
        st.session_state.flow_wrapper = wrap_flow()


def display_welcome_message():
    """Display welcome message for new users."""
    if not st.session_state.messages:
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown("""
            👋 **Welcome to the Software Leads Weekly Index Knowledge Base!**

            I'm here to help you with questions about:
            - 🎯 Software leadership and management
            - 🔧 Technical best practices
            - 👥 Team building and culture
            - 📈 Industry insights and trends

            **Try asking me anything about software leadership!**
            """)


def display_chat_history():
    """Display all messages in chat history."""
    for message in st.session_state.messages:
        avatar = "👤" if message["role"] == "user" else "🤖"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])


def process_chat_input():
    """Handle new chat input from user."""
    if prompt := st.chat_input("Ask me anything about software leadership... (type '/bye' to exit)", key="chat_input"):
        # Handle exit command
        if prompt.strip().lower() in ["/bye", "bye", "exit", "quit"]:
            handle_exit_command()

        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Display user message
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)

        # Get and display response
        with st.chat_message("assistant", avatar="🤖"):
            # Show typing indicator
            typing_placeholder = st.empty()
            show_typing_indicator(typing_placeholder)
            typing_placeholder.empty()

            # Process response
            with st.spinner("Processing your question... (This may take up to 2 minutes for the first question)"):
                try:
                    response = process_user_query(prompt, st.session_state.flow_wrapper)
                    st.markdown(response)
                except Exception as e:
                    response = f"❌ Sorry, I encountered an error: {str(e)}"
                    st.markdown(response)

        # Add assistant response to history
        st.session_state.messages.append({"role": "assistant", "content": response})


# =============================================================================
# VISUAL STYLING & DECORATIONS
# =============================================================================


def apply_custom_styles():
    """Apply custom CSS styling to the app."""
    st.markdown(
        """
    <style>
    .main-header {
        text-align: center;
        padding: 1rem 0 2rem 0;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .stChatMessage {
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .example-btn {
        margin: 0.2rem 0;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


def display_header():
    """Display the main header with styling."""
    st.markdown(
        """
    <div class="main-header">
        <h1>🚀 Software Leads Weekly Index KB</h1>
        <p style="font-size: 1.2em; margin: 0;">Your AI assistant for software leadership insights</p>
    </div>
    """,
        unsafe_allow_html=True,
    )


def display_footer():
    """Display footer with helpful tips."""
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666; padding: 1rem;'>"
        "💡 <strong>Tip:</strong> Try asking specific questions about software leadership, "
        "team management, or technical best practices for the best results!"
        "</div>",
        unsafe_allow_html=True,
    )


# =============================================================================
# MAIN APPLICATION FLOW
# =============================================================================


def main():
    """Main application entry point."""
    # Apply visual styling
    apply_custom_styles()
    display_header()

    # Initialize core app state
    initialize_session_state()

    # Display chat interface
    display_welcome_message()
    display_chat_history()

    # Handle user input
    process_chat_input()

    # Display footer
    display_footer()


# Run the app
if __name__ == "__main__":
    main()
else:
    # When imported or run by streamlit
    main()
