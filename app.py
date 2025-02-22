"""Streamlit app for the UI to query the RAG."""

from dataclasses import dataclass
import os
import signal
import streamlit as st
import torch
from queue import Queue
from flyde.flow import Flow
from flyde.io import EOF


# Fix streamlit torch classes path warning
torch.classes.__path__ = []  # type: ignore


# A structure to hold our appication's state
@dataclass
class FlowWrapper:
    flow: Flow
    query: Queue
    response: Queue


# Cache resource is a way to keep state between re-renders in Streamlit.
# wrap_flow() is effectively called just once in our app.
@st.cache_resource
def wrap_flow() -> FlowWrapper:
    # Load a PyFlyde flow from a .flyde file
    flow = Flow.from_file("Rag.flyde")

    # Get the query queue from the flow object
    query_q = flow.node.inputs["query"].queue
    # Attach a new queue to the flow's output
    response_q: Queue = Queue()
    flow.node.outputs["response"].connect(response_q)

    # Run the flow (in a separate thread)
    flow.run()

    return FlowWrapper(flow, query_q, response_q)


# UI header
st.title("Software Leads Weekly Index KB")
st.caption("A collection of articles, papers, and other resources for software leads.")
st.markdown("---")


f = wrap_flow()

query = st.text_input("Ask a question or type /bye to finish the conversation", "")
if query:
    if query.strip() == "/bye":
        query = EOF
    f.query.put(query)
    response = f.response.get()
    if response == EOF:
        st.write("Goodbye!")
        st.stop()
        os.kill(os.getpid(), signal.SIGKILL)
    else:
        st.write(response)
