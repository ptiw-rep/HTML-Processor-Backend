# 🧠 HTML Summarizer & Question Answering API

A FastAPI-based backend service for uploading HTML content, summarizing it using an LLM (via Ollama), and answering questions about it.

---

## 🔧 Requirements

Before running this application, ensure you have the following installed:

- [Python 3.10+](https://www.python.org/downloads/ )
- [Ollama](https://ollama.ai ) (for local LLM inference)
---

## 📦 Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/html-processor-api.git 
cd html-processor-api
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
uv sync
```
---

## ⚙️ Configuration

Create a `.env` file in the root directory with the following contents:

```env
MODEL_NAME=llama3
OLLAMA_URL=http://localhost:11434
```

> Replace `llama3` with any model available via Ollama (e.g., `mistral`, `phi3`, etc.)

---

## ▶️ Running the Application

### 1. Start Ollama

Make sure Ollama is running:

```bash
ollama serve
```

Then pull your chosen model:

```bash
ollama pull llama3
```

### 2. Run the FastAPI server

Using Uvicorn:

```bash
uvicorn main:app --reload
```

> Replace `main` with the actual name of your Python script if different (e.g., `app.py` → `app`)

The API will be accessible at:  
👉 http://localhost:8000

Swagger UI:  
👉 http://localhost:8000/docs

---

## 📝 API Usage Guide

### 1. Upload HTML Content

**POST** `/upload_html/`

**Body (JSON):**
```json
{
  "html": "<html><body><h1>Hello World</h1><p>This is some sample text.</p></body></html>"
}
```

**Response:**
```json
{
  "message": "HTML stored",
  "token": "abc123xyz"
}
```

Use the returned token for future operations.

---

### 2. Get Summary of HTML

**GET** `/get_summary/{token}`

Replace `{token}` with the token from the upload step.

**Example:**
```
http://localhost:8000/get_summary/abc123xyz
```

**Response:**
```json
{
  "summary": "This document contains a simple HTML page with a heading 'Hello World' and a paragraph."
}
```

---

### 3. Ask a Question About the HTML

**POST** `/ask/`

**Body (JSON):**
```json
{
  "token": "abc123xyz",
  "question": "What is the main heading of the document?"
}
```

**Response:**
```json
{
  "answer": "The main heading of the document is 'Hello World'."
}
```

---

## 🗑️ Automatic Cleanup

Uploaded HTML data is stored temporarily and automatically deleted after **1 hour**. A background task runs every **10 minutes** to clean up expired records.

---

## 📄 Logs

Logs are written to `app.log` and also printed to the console. The log file rotates when it reaches **5MB**, keeping up to **3 backups**.

Log levels used:
- `INFO`: Startup, shutdown, major events
- `WARNING`: Missing tokens or unexpected input
- `ERROR`: Exceptions or failed operations
- `DEBUG`: Database session lifecycle

---

## ✅ Testing

You can test the API using Swagger UI (`/docs`) or tools like `curl` or Postman.

---

## 🤖 Supported Models

Any model supported by Ollama can be used. Some popular ones include:

- `llama3`
- `mistral`
- `phi3`
- `gemma`
- `qwen2`

Update the `MODEL_NAME` in `.env` accordingly.

---

## 📌 Notes

- Ensure the `./data.db` SQLite file has proper write permissions.
- You can change database type (e.g., PostgreSQL) by updating `DATABASE_URL`.
- For better performance, consider using Gunicorn with Uvicorn workers in production.