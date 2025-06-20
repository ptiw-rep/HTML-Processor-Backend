import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, Text, DateTime, select, delete
from datetime import datetime, timedelta, timezone 
from uuid import uuid4
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_ollama import ChatOllama
from bs4 import BeautifulSoup
import tiktoken

os.environ["TIKTOKEN_CACHE_DIR"] = "./tiktoken_cache"

# ========== Configure Logging ==========
logger = logging.getLogger("server_app")
logger.setLevel(logging.ERROR)

# Create a rotating file handler
handler = RotatingFileHandler("app.log", maxBytes=5*1024*1024, backupCount=3)  # 5MB per file
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# Console handler for debugging
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Add both handlers
logger.addHandler(handler)
logger.addHandler(console_handler)

# ========== Settings ==========
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')
    model_name: str
    ollama_url: str
    tiktoken_encoding : str
    model_token_limit : int

settings = Settings()

# ========== Database Setup ==========
DATABASE_URL = "sqlite+aiosqlite:///./data.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class HTMLData(Base):
    __tablename__ = "html_data"
    token = Column(String, primary_key=True, index=True)
    html = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

async def init_db():
    logger.info("Initializing database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized.")

async def get_db():
    async with AsyncSessionLocal() as session:
        logger.debug("Database session created.")
        yield session
        logger.debug("Database session closed.")

# ========== Pydantic Models ==========
class HTMLPayload(BaseModel):
    html: str

class QueryPayload(BaseModel):
    token: str
    question: str

class FixGrammarPayload(BaseModel):
    text: str

class TranslatePayload(BaseModel):
    text: str
    targetLang: str

class InteractPayload(BaseModel):
    question: str
    selectedContent: str

# ========== Ollama LLM Declaration ==========
logger.info(f"Initializing LLM with model: {settings.model_name}")
llm = ChatOllama(
    model=settings.model_name,
    temperature=0.25
)

# ========== Ollama Helpers ==========
def summarize_html(html: str) -> str:
    logger.info("Summarizing HTML content...")
    messages = [
        {"role": "system", "content": """Summarize the following text content extracted from an HTML page.
                                         The summary should be concise and informative."""},
        {"role": "user", "content": html}
    ]
    try:
        response = llm.invoke(messages)
        logger.info("HTML summary generated.")
        return response.content
    except Exception as e:
        logger.error(f"Error summarizing HTML: {e}")
        raise

def ask_question(html: str, question: str) -> str:
    logger.info(f"Answering question: {question[:50]}...")  # Truncate long questions
    messages = [
        {"role": "system", "content": "You are answering questions based on the following text."},
        {"role": "user", "content": f"Text:\n{html}\n\nQuestion:\n{question}"}
    ]
    try:
        response = llm.invoke(messages)
        logger.info("Question answered successfully.")
        return response.content
    except Exception as e:
        logger.error(f"Error answering question: {e}")
        raise

# ========== HTML Cleanup to text ==========
def extract_text_from_html_string(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove non-visible tags
    for tag in soup(['script', 'style', 'head', 'title', 'meta', '[document]']):
        tag.decompose()

    # Helper function to check inline visibility
    def is_hidden(element):
        parent = element.parent
        if not parent:
            return False
        style = parent.attrs.get('style', '').replace(' ', '').lower()
        return 'display:none' in style or 'visibility:hidden' in style

    # Collect visible text
    visible_texts = [
        text.strip()
        for text in soup.find_all(string=True)
        if text.strip() and not is_hidden(text)
    ]

    return ' '.join(visible_texts)

# ========== Token Limiter ==========
def truncate_text_by_tokens(text, max_tokens=500, encoding_name="cl100k_base"):
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated_tokens = tokens[:max_tokens]
    return encoding.decode(truncated_tokens)

# ========== DB Cleanup Task ==========
expiration_time = timedelta(hours=1)
scheduler = AsyncIOScheduler()

async def cleanup_html():
    logger.info("Running scheduled cleanup task.")
    try:
        async with AsyncSessionLocal() as db:
            cutoff = datetime.now(timezone.utc) - expiration_time
            logger.info(f"Deleting records older than {cutoff}.")
            result = await db.execute(delete(HTMLData).where(HTMLData.timestamp < cutoff))
            deleted_rows = result.rowcount or 0
            await db.commit()
            logger.info(f"Cleaned up {deleted_rows} expired records.")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error during cleanup: {e}")

scheduler.add_job(cleanup_html, "interval", minutes=10)

# ========== Lifespan Handler ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FastAPI application.")
    await init_db()
    scheduler.start()
    logger.info("Scheduler started.")
    yield
    logger.info("Shutting down FastAPI application.")
    scheduler.shutdown()
    logger.info("Scheduler stopped.")

app = FastAPI(lifespan=lifespan)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Routes ==========
@app.post("/upload_html/")
async def upload_html(payload: HTMLPayload, db: AsyncSession = Depends(get_db)):
    logger.info("Received request to upload HTML.")
    try:
        token = str(uuid4())
        html_text = extract_text_from_html_string(payload.html)
        processed_html_text = truncate_text_by_tokens(html_text, settings.model_token_limit, settings.tiktoken_encoding)
        if not processed_html_text:
            logger.warning("No visible text found in HTML.")
            raise HTTPException(status_code=400, detail="No visible text found in HTML")
        db.add(HTMLData(token=token, html=processed_html_text))
        await db.commit()
        logger.info(f"HTML stored with token: {token}")
        return {"message": "HTML stored", "token": token}
    except Exception as e:
        logger.error(f"Error uploading HTML: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/get_summary/{token}")
async def get_summary(token: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"Request to get summary for token: {token}")
    result = await db.execute(select(HTMLData).where(HTMLData.token == token))
    html_data = result.scalar_one_or_none()
    if not html_data:
        logger.warning(f"Token {token} not found.")
        raise HTTPException(status_code=404, detail="Token not found")
    
    summary = summarize_html(html_data.html)
    return {"token": token, "summary": summary}

@app.post("/ask/")
async def ask_query(payload: QueryPayload, db: AsyncSession = Depends(get_db)):
    logger.info(f"Received question for token: {payload.token}")
    result = await db.execute(select(HTMLData).where(HTMLData.token == payload.token))
    html_data = result.scalar_one_or_none()
    if not html_data:
        logger.warning(f"Token {payload.token} not found.")
        raise HTTPException(status_code=404, detail="Token not found")

    answer = ask_question(html_data.html, payload.question)
    return {"answer": answer}

@app.post("/correct-grammar/")
async def correct_grammar(payload: FixGrammarPayload):
    logger.info("Correcting grammar for provided text.")
    messages = [
        {"role": "system", "content": """You are a grammar correction assistant. 
                                         Correct the grammar and fix the typo required in the provided text."""},
        {"role": "user", "content": payload.text}
    ]
    try:
        response = llm.invoke(messages)
        logger.info("Grammar correction completed.")
        return {"corrected_text": response.content}
    except Exception as e:
        logger.error(f"Error correcting grammar: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/translate/")
async def translate_text(payload: TranslatePayload):
    logger.info(f"Translating text to {payload.targetLang}.")
    messages = [
        {"role": "system", "content": f"""You are a translation assistant. 
                                          Translate the following text to {payload.targetLang}."""},
        {"role": "user", "content": payload.text}
    ]
    try:
        response = llm.invoke(messages)
        logger.info("Translation completed.")
        return {"translated_text": response.content}
    except Exception as e:
        logger.error(f"Error translating text: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/chat_about_content/")
async def chat_about_content(payload: InteractPayload):
    logger.info("Genie started working.")
    messages = [
        {"role": "system", "content": """Given the following content, answer the user's question. 
                                         If it is a task complete the task and only return the results."""},
        {"role": "system", "content": f"Content:\n{payload.selectedContent}\n"},
        {"role": "user", "content": f"Question or Task:\n{payload.question}\n"}
    ]
    try:
        response = llm.invoke(messages)
        logger.info("Genie work completed.")
        return {"answer": response.content}
    except Exception as e:
        logger.error(f"Error on Genie task completion: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
