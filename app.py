import streamlit as st
import os
import tempfile
import re
import time
import random
from PyPDF2 import PdfReader
import pdfplumber
from docx import Document  # For Word files
import openpyxl  # For Excel files
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv
import google.generativeai as genai
import logging
import uuid  # For generating unique session IDs

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up Streamlit page
st.set_page_config(page_title="DeepDocAI", page_icon="🤖", layout="wide")

# Load environment variables
try:
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables")
    genai.configure(api_key=api_key)
except Exception as e:
    logger.error(f"Error configuring Google API: {str(e)}")
    st.error(f"Error configuring Google API: {str(e)}")

# Custom CSS (unchanged)
st.markdown("""
    <style>
    h1, .stHeader { border-bottom: none !important; }
    .chat-bubble {
        background-color: #DCF8C6; color: black; padding: 12px; border-radius: 12px; max-width: 80%;
        margin: 10px 0 !important; display: inline-block; font-size: 18px; line-height: 1.4;
        box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.1); animation: fadeIn 0.5s ease-in-out, bounce 0.5s ease-in-out;
    }
    .ai-bubble {
        background-color: #ECECEC; color: black; padding: 12px; border-radius: 12px; max-width: 80%;
        margin: 10px 0 !important; display: inline-block; font-size: 18px; line-height: 1.6;
        box-shadow: 2px 2px 10px rgba(0, 0, 0, 0.1); animation: fadeIn 0.5s ease-in-out, bounce 0.5s ease-in-out;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
    }
    .typing { font-size: 14px; color: #888; animation: blink 1.5s infinite; }
    @keyframes blink { 0% { opacity: 0.2; } 50% { opacity: 1; } 100% { opacity: 0.2; } }
    .ai-response { animation: slideIn 0.5s ease-in-out; }
    @keyframes slideIn { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
    .user-response { animation: slideInRight 0.5s ease-in-out; }
    @keyframes slideInRight { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
    .message-container { text-align: left; width: 100%; max-width: 800px; margin: 0px !important; padding: 0px !important; overflow: hidden; }
    .pagination-container { min-height: 400px; display: flex; flex-direction: column; justify-content: flex-start; align-items: center; padding: 0px !important; margin: 0px !important; overflow: hidden; }
    .nav-buttons { display: flex; justify-content: space-between; align-items: center; margin-top: 20px; width: 100%; max-width: 800px; }
    .nav-button { background-color: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; min-width: 120px; text-align: center; }
    .nav-button:disabled { background-color: #cccccc; cursor: not-allowed; }
    .stChatMessage { display: none !important; }
    .sidebar-input-container { background-color: #fff; border: 1px solid #ddd; border-radius: 20px; padding: 10px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); display: flex; align-items: center; gap: 8px; margin-top: 0px !important; margin-bottom: 0px !important; }
    .input-wrapper { position: relative; flex-grow: 1; }
    .stTextInput > div > div > input { border: none !important; outline: none !important; padding: 8px 40px 8px 30px !important; font-size: 14px; width: 100%; border-radius: 20px; }
    .mic-button { background: none; border: none; cursor: pointer; font-size: 16px; color: #555; }
    .mic-button.listening { color: blue; animation: pulse 1s infinite; }
    @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.2); } 100% { transform: scale(1); } }
    .submit-button { background: none !important; border: none !important; padding: 0 !important; cursor: pointer !important; font-size: 16px !important; color: #4CAF50 !important; }
    .stApp { margin: 0px !important; padding: 0px !important; }
    </style>
""", unsafe_allow_html=True)

# File Processing Functions (unchanged)
def extract_tables_from_pdf(pdf_path):
    tables_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        tables_text += "| " + " | ".join(str(cell) for cell in table[0]) + " |\n"
                        tables_text += "| " + " | ".join(["---"] * len(table[0])) + " |\n"
                        for row in table[1:]:
                            tables_text += "| " + " | ".join(str(cell) for cell in row) + " |\n"
                        tables_text += "\n"
    except Exception as e:
        logger.error(f"Error extracting tables from PDF: {str(e)}")
        st.error(f"Error extracting tables from PDF: {str(e)}")
    return tables_text

def process_pdf(pdf):
    logger.info("Starting PDF processing")
    text = ""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf.getbuffer())
            temp_path = temp_file.name
        logger.info("PDF temp file created: %s", temp_path)

        pdf_reader = PdfReader(temp_path)
        for page in pdf_reader.pages:
            extracted_text = page.extract_text()
            if extracted_text:
                text += extracted_text + "\n\n"

        tables_text = extract_tables_from_pdf(temp_path)
        if tables_text.strip():
            text += "**Extracted Tables:**\n" + tables_text + "\n\n"
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        st.error(f"Error processing PDF: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
    logger.info("PDF processing completed")
    return text

def process_docx(docx):
    logger.info("Starting DOCX processing")
    text = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
            temp_file.write(docx.getbuffer())
            temp_path = temp_file.name
            doc = Document(temp_path)
            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text + "\n\n"
            for table in doc.tables:
                table_text = ""
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells)
                    table_text += row_text + "\n"
                if table_text.strip():
                    text += "**Extracted Table from Word:**\n" + table_text + "\n\n"
            os.remove(temp_path)
    except Exception as e:
        logger.error(f"Error processing Word file: {str(e)}")
        st.error(f"Error processing Word file: {str(e)}")
    return text

def process_xlsx(xlsx):
    logger.info("Starting XLSX processing")
    text = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
            temp_file.write(xlsx.getbuffer())
            temp_path = temp_file.name
            wb = openpyxl.load_workbook(temp_path)
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                text += f"**Sheet: {sheet_name}**\n"
                for row in sheet.rows:
                    row_text = " | ".join(str(cell.value) if cell.value is not None else "" for cell in row)
                    if row_text.strip():
                        text += row_text + "\n"
                text += "\n"
            os.remove(temp_path)
    except Exception as e:
        logger.error(f"Error processing Excel file: {str(e)}")
        st.error(f"Error processing Excel file: {str(e)}")
    return text

def get_file_text(docs):
    logger.info("Extracting text from files")
    text = ""
    if not docs:
        return text
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for doc in docs:
                if doc.name.endswith('.pdf'):
                    futures.append(executor.submit(process_pdf, doc))
                elif doc.name.endswith('.docx'):
                    futures.append(executor.submit(process_docx, doc))
                elif doc.name.endswith('.xlsx'):
                    futures.append(executor.submit(process_xlsx, doc))
            for future in futures:
                text += future.result() + "\n"
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")
        st.error(f"Processing failed: {str(e)}")
    logger.info("Text extraction completed: %d characters", len(text))
    return text

def get_text_chunks(text):
    try:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=5000, chunk_overlap=500)
        return text_splitter.split_text(text)
    except Exception as e:
        logger.error(f"Error splitting text: {str(e)}")
        st.error(f"Error splitting text: {str(e)}")
        return []

def get_vector_store(text_chunks, session_id):
    if not text_chunks:
        logger.error("No text found in the uploaded files")
        st.error("❌ No text found in the uploaded files.")
        return False
    try:
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        vector_store = FAISS.from_texts(text_chunks, embedding=embeddings)
        # Save to a session-specific folder
        session_folder = f"faiss_index_{session_id}"
        os.makedirs(session_folder, exist_ok=True)
        vector_store.save_local(session_folder)
        logger.info(f"Vector store created successfully for session {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error in vector storage: {str(e)}")
        st.error(f"⚠️ Error in vector storage: {e}")
        return False

# AI Interaction Functions
prompt_template = """
You are an advanced AI assistant with strong reasoning capabilities. Your task is to provide **clear, well-structured, and fact-based answers** strictly using the given context.

### **Guidelines:**  
1. If the answer **exists in the context**, provide a **concise, direct, and well-explained response**.  
2. If the answer **is not found directly**, analyze the context carefully:  
   - If the context provides indirect hints, use reasoning to give the most accurate answer possible.  
   - If the context explicitly states the **opposite** of what is being asked, state that clearly.  
   - If the answer is **completely unavailable**, respond in a human-like way by saying:  
     **"No, [subject] does not [action]."**  
     or  
     **"There is no information available in the provided context to determine this."**  
3. **Use bullet points and line breaks for clarity when listing multiple points.**  
4. **Never make up information that is not in the context.**  

### **Context:**  
{context}  

### **User Question:**  
{question}  

### **Answer:**  
"""

def get_conversational_chain():
    prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
    model = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.3)
    return load_qa_chain(model, chain_type="stuff", prompt=prompt)

def format_response(response_text):
    formatted_text = re.sub(r'-\n', '', response_text)
    formatted_text = re.sub(r'^\s*\*+\s+', '• ', formatted_text, flags=re.MULTILINE)
    formatted_text = formatted_text.replace("\n-", "\n\n• ")
    formatted_text = formatted_text.replace("-", " - ")
    formatted_text = re.sub(r'\n\s*\n+', '\n\n', formatted_text)
    formatted_text = "\n\n".join([line.strip() for line in formatted_text.split("\n") if line.strip()])
    return formatted_text

def display_response(response_text, chat_placeholder):
    formatted_text = format_response(response_text)
    with chat_placeholder:
        st.markdown(
            f'<div class="message-container"><div class="ai-bubble ai-response">{formatted_text}</div></div>',
            unsafe_allow_html=True
        )

def user_input(user_question, chat_placeholder, session_id):
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    session_folder = f"faiss_index_{session_id}"
    new_db = FAISS.load_local(session_folder, embeddings, allow_dangerous_deserialization=True)

    docs = new_db.similarity_search(user_question)
    chain = get_conversational_chain()

    with chat_placeholder:
        st.markdown(
            f'<div class="message-container"><div class="chat-bubble user-response">🧑‍💼 You: {user_question}</div></div>',
            unsafe_allow_html=True
        )

    response = chain(
        {"input_documents": docs, "question": user_question},
        return_only_outputs=True
    )

    response_text = format_response(response["output_text"])
    
    display_response(response_text, chat_placeholder)
    st.session_state[f"conversation_{session_id}"].append({"role": "ai", "content": response_text})

def main():
    logger.info("App started")
    
    # Generate or retrieve a unique session ID for this user
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    session_id = st.session_state.session_id

    # Initialize session-specific state
    if f"conversation_{session_id}" not in st.session_state:
        st.session_state[f"conversation_{session_id}"] = []
    if f"current_page_{session_id}" not in st.session_state:
        st.session_state[f"current_page_{session_id}"] = 0
    if f"processed_{session_id}" not in st.session_state:
        st.session_state[f"processed_{session_id}"] = False
    if f"docs_{session_id}" not in st.session_state:
        st.session_state[f"docs_{session_id}"] = []

    chat_placeholder = st.container()

    if st.session_state[f"conversation_{session_id}"]:
        message_pairs = []
        for i in range(0, len(st.session_state[f"conversation_{session_id}"]), 2):
            pair = [st.session_state[f"conversation_{session_id}"][i]]
            if i + 1 < len(st.session_state[f"conversation_{session_id}"]):
                pair.append(st.session_state[f"conversation_{session_id}"][i + 1])
            message_pairs.append(pair)
        
        total_pages = len(message_pairs)
        current_page = st.session_state[f"current_page_{session_id}"]
        
        if total_pages > 0:
            with chat_placeholder:
                st.markdown('<div class="message-container">', unsafe_allow_html=True)
                for message in message_pairs[current_page]:
                    if message["role"] == "user":
                        st.markdown(
                            f'<div class="chat-bubble user-response">🧑‍💼 You: {message["content"]}</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f'<div class="ai-bubble ai-response">{message["content"]}</div>',
                            unsafe_allow_html=True
                        )
                st.markdown('</div>', unsafe_allow_html=True)
            
            with chat_placeholder:
                st.markdown('<div class="nav-buttons">', unsafe_allow_html=True)
                col1, col2, col3 = st.columns([1, 1, 1])
                
                with col1:
                    if st.button("← Previous", key=f"prev_{session_id}", disabled=current_page == 0, use_container_width=True):
                        st.session_state[f"current_page_{session_id}"] = max(0, current_page - 1)
                        st.rerun()
                
                with col2:
                    st.markdown(f"<div style='text-align: center;'>Page {current_page + 1} of {total_pages}</div>", unsafe_allow_html=True)
                
                with col3:
                    if st.button("Next →", key=f"next_{session_id}", disabled=current_page == total_pages - 1, use_container_width=True):
                        st.session_state[f"current_page_{session_id}"] = min(total_pages - 1, current_page + 1)
                        st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)

    with st.sidebar:
        st.title("🚀 DeepDocAI")
        st.subheader("📂 Upload Documents:")
        docs = st.file_uploader(
            "Upload PDFs, Word (.docx), or Excel (.xlsx) files and Click on Submit",
            accept_multiple_files=True,
            type=['pdf', 'docx', 'xlsx'],
            key=f"file_uploader_{session_id}"
        )
        
        if st.button("📥 Submit & Process", key=f"submit_button_{session_id}"):
            logger.info(f"Submit button clicked for session {session_id}")
            if not docs:
                st.warning("⚠️ Please upload at least one file")
            else:
                st.session_state[f"docs_{session_id}"] = docs
                logger.info(f"Processing files for session {session_id}")
                
                with st.spinner("Processing your files... Please wait."):
                    raw_text = get_file_text(docs)
                    if not raw_text.strip():
                        st.error("❌ Failed to extract text from files.")
                    else:
                        text_chunks = get_text_chunks(raw_text)
                        if get_vector_store(text_chunks, session_id):
                            st.session_state[f"processed_{session_id}"] = True
                            st.success("✅ Process Done! Your files have been successfully processed.")

        with st.form(key=f"input_form_{session_id}", clear_on_submit=True):
            col1, col2 = st.columns([12, 1])
            with col1:
                user_question = st.text_input(
                    "Ask a question...",
                    placeholder="Type your question here...",
                    label_visibility="collapsed",
                    value=""
                )
            with col2:
                submit_button = st.form_submit_button("➤", use_container_width=False)

    if submit_button and user_question:
        st.session_state[f"conversation_{session_id}"].append({"role": "user", "content": user_question})
        user_input(user_question, chat_placeholder, session_id)
        st.session_state[f"current_page_{session_id}"] = (len(st.session_state[f"conversation_{session_id}"]) // 2) - 1
        st.rerun()

    logger.info(f"Main loop completed for session {session_id}")

if __name__ == "__main__":
    main()
